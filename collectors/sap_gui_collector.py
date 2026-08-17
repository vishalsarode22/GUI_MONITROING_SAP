"""
GUI-based SAP monitoring collector for T-codes, using SAP GUI Scripting.
Each action function receives a `capture(suffix)` callback it can call
one or more times, so multi-step T-codes (e.g. ST22) can take a
screenshot at each meaningful checkpoint, not just once at the end.

Action functions may also return a dict of extracted real data via
SAP GUI Scripting (e.g. lock counts, server counts). Additionally, OCR
(Tesseract) is run on the most recent screenshot for any T-code that
has patterns defined in config/ocr_patterns.yaml, filling in values
that scripting couldn't reach directly.
"""

import time
from sap_gui.scripting_connection import get_scripting_session, get_active_session
from sap_gui.tcode_actions import ACTIONS
from sap_gui.screenshot import capture_screenshot
from sap_gui.ocr_extractor import run_ocr, extract_patterns
from core.config_loader import get_ocr_patterns
from core.models import MetricResult, Status
from utils.logger import get_logger

log = get_logger(__name__, "sap_gui_collector")


def collect_tcode_evidence(tasks: list[dict]) -> list[MetricResult]:
    results = []

    try:
        session = get_active_session() or get_scripting_session()
    except Exception as e:
        log.error(f"Could not acquire scripting session: {e}")
        return results

    if not session:
        log.error("No active SAP GUI session available for evidence collection.")
        return results

    all_ocr_patterns = get_ocr_patterns()

    for task in tasks:
        tcode = task.get("tcode", "").strip().upper()
        action_name = task.get("action", "simple")
        screenshots = []

        if not tcode:
            continue

        # Verify session is still valid before each task; reconnect if dropped
        try:
            if getattr(session, "Children", None) is None:
                session = get_scripting_session(max_retries=3)
        except Exception:
            session = get_scripting_session(max_retries=3)

        if not session:
            log.error(f"Session disconnected before executing {tcode}. Skipping.")
            break

        def capture(suffix: str = ""):
            name = f"{tcode}_{suffix}" if suffix else tcode
            path = capture_screenshot(session, name)
            if path:
                screenshots.append(path)
            return path

        try:
            action_fn = ACTIONS.get(action_name)
            if not action_fn:
                raise ValueError(f"No action registered for '{action_name}'")

            extracted_data = action_fn(session, capture) or {}
            log.info(f"Extracted data for {tcode} (scripting): {extracted_data}")

            if not screenshots:
                # Fallback capture if action didn't trigger one
                capture()

            # --- OCR fallback: fill in values scripting couldn't reach ---
            ocr_patterns = all_ocr_patterns.get(tcode, {})
            if ocr_patterns and screenshots:
                try:
                    ocr_text = run_ocr(screenshots[-1])
                    ocr_data = extract_patterns(ocr_text, ocr_patterns)
                    for k, v in ocr_data.items():
                        extracted_data.setdefault(k, v)
                    if ocr_data:
                        log.info(f"OCR extracted for {tcode}: {ocr_data}")
                    else:
                        log.info(f"OCR found no matches for {tcode} (patterns: {list(ocr_patterns.keys())})")
                except Exception as ex_ocr:
                    log.warning(f"OCR processing failed for {tcode}: {ex_ocr}")

            results.append(MetricResult(
                name=f"screenshot_{tcode}",
                value=None,
                display_value=f"captured ({len(screenshots)})",
                status=Status.NORMAL if extracted_data else Status.UNKNOWN,
                source="sap_gui_collector",
                tcode=tcode,
                detail=f"action={action_name}",
                screenshot_path=screenshots[0] if screenshots else None,
                screenshot_paths=screenshots,
                extra_data=extracted_data,
            ))

        except Exception as e:
            log.error(f"Failed to collect T-code {tcode} (action={action_name}): {e}")
            results.append(MetricResult(
                name=f"screenshot_{tcode}",
                value=None,
                display_value="failed",
                status=Status.UNKNOWN,
                source="sap_gui_collector",
                tcode=tcode,
                detail=f"action={action_name}, error={e}",
                screenshot_paths=[],
                extra_data={},
            ))

        time.sleep(0.3)

    log.info(f"Collected evidence for {len(results)} T-codes.")
    return results