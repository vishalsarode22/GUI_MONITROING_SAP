"""
Orchestrator: runs one full monitoring cycle for a single SAP system/client.
Combines all collectors (Linux, SAP process, ...) into a single MonitoringResult.
Each collector is isolated -- if one fails, others still run and the failure
is recorded in MonitoringResult.errors rather than crashing the cycle.

Linux/SAP-process (OS-level) metrics are only collected if ssh_creds with
a host is provided. Systems without SSH/OS access simply skip that section
cleanly, without erroring -- SAP GUI T-code monitoring (handled separately
in main.py) still runs regardless.
"""

from core.models import MonitoringResult
from core.config_loader import (
    get_linux_ssh_credentials,
    get_sap_instance_nr,
    get_thresholds,
    get_smtp_config,
)
from collectors.linux_collector import collect_linux_metrics, parse_linux_metrics
from collectors.sap_process_collector import collect_sap_process_list, parse_sap_process_list
from evaluation.threshold_engine import evaluate_all
from evaluation.ai_analyzer import analyze as run_ai_analysis
from notifications.email_alert import send_critical_alert
from utils.logger import get_logger

log = get_logger(__name__, "monitoring")


def run_monitoring_cycle(system: str, client: str, ssh_creds: dict = None) -> MonitoringResult:
    """
    Runs one monitoring cycle: collects Linux + SAP process metrics
    (if SSH access is available), evaluates thresholds, runs AI analysis,
    sends alert if critical, and returns a single MonitoringResult.

    ssh_creds: optional per-system SSH connection details
    (host/port/username/password).
      - If None: falls back to .env-based single-system credentials
        (original single-system behavior, e.g. python main.py).
      - If a dict with an empty/missing "host": OS-level collection is
        skipped entirely (system has GUI-only access, no SSH).
      - If a dict with a real "host": used directly for OS-level collection.
    """
    result = MonitoringResult(system=system, client=client)
    thresholds = get_thresholds()

    has_ssh = ssh_creds is not None and bool(ssh_creds.get("host"))

    if not has_ssh and ssh_creds is None:
        # No explicit ssh_creds passed at all -- fall back to .env defaults
        try:
            ssh_creds = get_linux_ssh_credentials()
            has_ssh = True
        except Exception:
            has_ssh = False

    if has_ssh:
        # --- Linux metrics ---
        try:
            raw_linux = collect_linux_metrics(**ssh_creds)
            linux_metrics = parse_linux_metrics(raw_linux)
            linux_metrics = evaluate_all(linux_metrics, thresholds)
            result.metrics.extend(linux_metrics)
            if "error" in raw_linux:
                result.errors.append(f"linux_collector: {raw_linux['error']}")
        except Exception as e:
            log.error(f"Linux collector failed entirely: {e}")
            result.errors.append(f"linux_collector: {e}")

        # --- SAP process metrics ---
        try:
            instance_nr = get_sap_instance_nr()
            raw_sap = collect_sap_process_list(**ssh_creds, instance_nr=instance_nr)
            sap_metrics = parse_sap_process_list(raw_sap)
            result.metrics.extend(sap_metrics)
            if "error" in raw_sap:
                result.errors.append(f"sap_process_collector: {raw_sap['error']}")
        except Exception as e:
            log.error(f"SAP process collector failed entirely: {e}")
            result.errors.append(f"sap_process_collector: {e}")
    else:
        log.info(f"No SSH access configured for {system} -- skipping Linux/OS-level metrics (SAP GUI evidence only).")

    result.compute_overall_status()

    log.info(
        f"Monitoring cycle complete for {system}/{client}: "
        f"overall={result.overall_status.value}, "
        f"metrics={len(result.metrics)}, errors={len(result.errors)}"
    )

    # --- Immediate alert on CRITICAL ---
    if result.overall_status.value == "CRITICAL":
        try:
            smtp_config = get_smtp_config()
            send_critical_alert(result, smtp_config)
        except Exception as e:
            log.error(f"Failed to send critical alert: {e}")
            result.errors.append(f"email_alert: {e}")

    # --- AI analysis (mock or real depending on USE_MOCK_AI) ---
    try:
        result.ai_analysis = run_ai_analysis(result)
    except Exception as e:
        log.error(f"AI analysis step failed entirely: {e}")
        result.errors.append(f"ai_analyzer: {e}")

    return result