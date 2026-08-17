"""
AI-based root cause analysis and troubleshooting recommendations.
The deterministic monitoring engine (threshold_engine.py) decides severity --
this module only asks the AI to explain WHY and WHAT TO DO, given already-
classified facts. Never sends passwords or secrets to the AI.

USE_MOCK_AI controls whether this calls a real LLM API (Google Gemini,
free tier) or returns a data-consistent canned response, so the rest of
the pipeline can be built and tested before an API key is available.
"""

import os
from core.models import MonitoringResult, AIAnalysis
from utils.logger import get_logger

log = get_logger(__name__, "ai")

USE_MOCK_AI = os.getenv("USE_MOCK_AI", "true").lower() == "true"


def _build_prompt(result: MonitoringResult) -> str:
    """
    Builds the context sent to the AI. Only facts -- no credentials,
    no passwords, nothing sensitive beyond system/client identifiers.
    """
    lines = [
        f"System: {result.system}",
        f"Client: {result.client}",
        f"Overall Status: {result.overall_status.value}",
        "",
        "Metrics:",
    ]
    for m in result.metrics:
        lines.append(f"- {m.name}: {m.display_value} [{m.status.value}] {m.detail}".strip())

    if result.errors:
        lines.append("")
        lines.append("Collector errors:")
        for e in result.errors:
            lines.append(f"- {e}")

    lines.append("")
    lines.append(
        "You are an SAP BASIS expert. Analyze the above monitoring data. "
        "Respond ONLY in this exact structured format, with no extra "
        "preamble or markdown formatting:\n"
        "SEVERITY: <CRITICAL|WARNING|NORMAL>\n"
        "LIKELY ROOT CAUSE: <one or two sentences>\n"
        "EVIDENCE:\n- <bullet>\n- <bullet>\n"
        "RECOMMENDED ACTIONS:\n1. <step>\n2. <step>\n"
        "CONFIDENCE: <HIGH|MEDIUM|LOW>\n"
        "Clearly distinguish observed facts from inference and recommendation. "
        "Never claim an action was performed -- only recommend."
    )
    return "\n".join(lines)


def _parse_ai_response(raw_text: str) -> AIAnalysis:
    """
    Parses the AI's structured text response into an AIAnalysis object.
    Tolerant of minor formatting variation -- falls back to storing
    raw_response if parsing fails.
    """
    analysis = AIAnalysis(raw_response=raw_text)

    try:
        lines = raw_text.splitlines()
        section = None
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.upper().startswith("SEVERITY:"):
                analysis.severity = stripped.split(":", 1)[1].strip()
                section = None
            elif stripped.upper().startswith("LIKELY ROOT CAUSE:"):
                analysis.likely_root_cause = stripped.split(":", 1)[1].strip()
                section = None
            elif stripped.upper().startswith("EVIDENCE"):
                section = "evidence"
            elif stripped.upper().startswith("RECOMMENDED ACTIONS"):
                section = "actions"
            elif stripped.upper().startswith("CONFIDENCE:"):
                analysis.confidence = stripped.split(":", 1)[1].strip()
                section = None
            elif section == "evidence" and stripped.startswith("-"):
                analysis.evidence.append(stripped.lstrip("- ").strip())
            elif section == "actions":
                cleaned = stripped.lstrip("0123456789. ").strip()
                if cleaned:
                    analysis.recommended_actions.append(cleaned)
    except Exception as e:
        log.error(f"Failed to parse AI response, keeping raw only: {e}")

    return analysis


def _call_mock_ai(prompt: str, result: MonitoringResult = None) -> str:
    """
    Generates a mock response that reflects the ACTUAL MonitoringResult,
    so reports stay internally consistent (e.g. don't show 'CRITICAL' AI
    analysis when overall status is NORMAL). Used when USE_MOCK_AI=true
    or as a fallback if the real AI call fails.
    """
    log.info("USE_MOCK_AI=true -- returning mock AI response based on real result data.")

    if result is None:
        return (
            "SEVERITY: UNKNOWN\n"
            "LIKELY ROOT CAUSE: No monitoring data available for analysis.\n"
            "EVIDENCE:\n- No data provided\n"
            "RECOMMENDED ACTIONS:\n1. Re-run monitoring cycle.\n"
            "CONFIDENCE: LOW\n"
        )

    critical = result.critical_metrics()
    warning = [m for m in result.metrics if m.status.value == "WARNING"]

    if result.overall_status.value == "CRITICAL" and critical:
        evidence_lines = "\n".join(f"- {m.name}: {m.display_value} ({m.detail})" for m in critical)
        actions = "\n".join(
            f"{i+1}. Investigate {m.name} (currently {m.display_value}, "
            f"threshold {m.threshold_warning}/{m.threshold_critical})."
            for i, m in enumerate(critical)
        )
        return (
            "SEVERITY: CRITICAL\n"
            f"LIKELY ROOT CAUSE: {len(critical)} metric(s) exceeded critical thresholds, "
            "indicating a resource or process issue requiring immediate attention.\n"
            f"EVIDENCE:\n{evidence_lines}\n"
            f"RECOMMENDED ACTIONS:\n{actions}\n"
            f"{len(critical)+1}. Verify whether the condition is still occurring before escalating.\n"
            "CONFIDENCE: MEDIUM\n"
        )

    if result.overall_status.value == "WARNING" and warning:
        evidence_lines = "\n".join(f"- {m.name}: {m.display_value} ({m.detail})" for m in warning)
        return (
            "SEVERITY: WARNING\n"
            f"LIKELY ROOT CAUSE: {len(warning)} metric(s) are approaching threshold limits "
            "but have not yet reached critical levels.\n"
            f"EVIDENCE:\n{evidence_lines}\n"
            "RECOMMENDED ACTIONS:\n1. Monitor these metrics over the next few cycles.\n"
            "2. Investigate if the trend continues upward.\n"
            "CONFIDENCE: MEDIUM\n"
        )

    return (
        "SEVERITY: NORMAL\n"
        "LIKELY ROOT CAUSE: No issues detected. All monitored metrics are within "
        "configured thresholds.\n"
        f"EVIDENCE:\n- {len(result.metrics)} metrics evaluated, all NORMAL\n"
        "RECOMMENDED ACTIONS:\n1. No action required. Continue routine monitoring.\n"
        "CONFIDENCE: HIGH\n"
    )


def _call_real_ai(prompt: str) -> str:
    """
    Calls Google Gemini (free tier) for real AI analysis.
    Requires GEMINI_API_KEY in .env.
    This model has "thinking" enabled by default and may return the
    response split across multiple parts, some marked as internal
    reasoning ("thought": true). We filter those out and join only the
    actual answer text, rather than trying to disable thinking mode
    (which this model/API version rejects as an invalid argument).
    Raises on failure -- analyze() catches this and falls back safely.
    """
    import requests

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env -- cannot call real AI.")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-flash-latest:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
    }

    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(
            p.get("text", "") for p in parts if not p.get("thought", False)
        )
        if not text.strip():
            raise RuntimeError("No non-thought text found in Gemini response.")
        return text
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response shape: {data}") from e

def analyze(result: MonitoringResult) -> AIAnalysis:
    """
    Main entry point: builds prompt from MonitoringResult, calls AI
    (mock or real depending on USE_MOCK_AI), parses response, returns
    AIAnalysis. Never raises -- on failure, falls back to the
    data-consistent mock response so a flaky API call never breaks
    the pipeline, and logs the error for visibility.
    """
    prompt = _build_prompt(result)

    try:
        if USE_MOCK_AI:
            raw_text = _call_mock_ai(prompt, result)
        else:
            try:
                raw_text = _call_real_ai(prompt)
            except Exception as e:
                log.warning(f"Real AI call failed, falling back to mock: {e}")
                raw_text = _call_mock_ai(prompt, result)

        analysis = _parse_ai_response(raw_text)
        log.info(f"AI analysis complete: severity={analysis.severity}, confidence={analysis.confidence}")
        return analysis
    except Exception as e:
        log.error(f"AI analysis failed entirely: {e}")
        return AIAnalysis(raw_response=f"AI analysis failed: {e}")