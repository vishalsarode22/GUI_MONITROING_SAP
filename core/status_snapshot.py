"""
Writes/reads a JSON snapshot per system, synthesizing dynamic SAP GUI T-Code metrics
so each system displays its own unique, real-time values.
"""

import json
import os
from datetime import datetime
from utils.logger import get_logger

log = get_logger(__name__, "application")

SNAPSHOT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "snapshots"
)


def _snapshot_path(system_name: str) -> str:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    safe_name = "".join(c for c in system_name if c.isalnum() or c in "-_")
    return os.path.join(SNAPSHOT_DIR, f"{safe_name}.json")


def _build_metrics_from_gui(gui_evidence: list, system_name: str) -> list:
    """
    Builds distinct metrics dynamically from the actual extracted T-Code evidence for this specific system.
    """
    evidence_map = {}
    for item in gui_evidence:
        tcode = item.get("tcode", "")
        extra = item.get("extra_data", {})
        display = item.get("display_value", "")
        evidence_map[tcode] = {"extra": extra if isinstance(extra, dict) else {}, "display": display}

    metrics = []

    # 1. AL08 - User sessions
    al08_disp = evidence_map.get("AL08", {}).get("display")
    if al08_disp:
        metrics.append({
            "name": "Active User Sessions (AL08)",
            "display_value": al08_disp,
            "status": "OK",
            "detail": f"Connected users on {system_name}"
        })

    # 2. SM12 - Enqueue Locks
    sm12_extra = evidence_map.get("SM12", {}).get("extra", {})
    locks = sm12_extra.get("lock_count")
    if locks is not None:
        try:
            locks = int(locks)
            status = "CRITICAL" if locks > 20 else ("WARNING" if locks > 10 else "OK")
            metrics.append({
                "name": "SAP Enqueue Locks (SM12)",
                "display_value": f"{locks} active lock(s)",
                "status": status,
                "detail": "Table enqueue lock entries"
            })
        except Exception:
            pass

    # 3. SM13 - Update Tasks
    sm13_disp = evidence_map.get("SM13", {}).get("display")
    if sm13_disp:
        metrics.append({
            "name": "Update Requests (SM13)",
            "display_value": sm13_disp,
            "status": "OK" if ("0" in sm13_disp or "no" in sm13_disp.lower()) else "WARNING",
            "detail": "V1/V2 Update tasks"
        })

    # 4. SM37 - Background Jobs
    sm37_act = evidence_map.get("SM37", {}).get("extra", {}).get("active_jobs", 0)
    sm37_canc = evidence_map.get("SM37_CANCELLED", {}).get("extra", {}).get("cancelled_jobs", 0)
    metrics.append({
        "name": "Background Jobs (SM37)",
        "display_value": f"Active: {sm37_act} | Cancelled: {sm37_canc}",
        "status": "CRITICAL" if int(sm37_canc) > 0 else "OK",
        "detail": "Job scheduler status"
    })

    # 5. SM51 - Instances
    sm51_extra = evidence_map.get("SM51", {}).get("extra", {})
    inst = sm51_extra.get("instances_started")
    if inst is not None:
        metrics.append({
            "name": "Active Instances (SM51)",
            "display_value": f"{inst} instance(s)",
            "status": "OK",
            "detail": "Application server nodes"
        })

    # 6. SM66 - Global Work Processes
    sm66_procs = evidence_map.get("SM66", {}).get("extra", {}).get("running_processes", 0)
    metrics.append({
        "name": "Active Work Processes (SM66)",
        "display_value": f"{sm66_procs} process(es) running",
        "status": "OK",
        "detail": "DIA/BGD/UPD processes"
    })

    # 7. SM58 - tRFC Backlog
    sm58_disp = evidence_map.get("SM58", {}).get("display")
    if sm58_disp:
        metrics.append({
            "name": "tRFC Errors / Backlog (SM58)",
            "display_value": sm58_disp,
            "status": "OK" if ("nothing" in sm58_disp.lower() or "0" in sm58_disp) else "WARNING",
            "detail": "Transactional RFC queue"
        })

    # 8. ST22 - ABAP Short Dumps
    st22_extra = evidence_map.get("ST22", {}).get("extra", {})
    dumps = st22_extra.get("dump_count")
    if dumps is not None:
        try:
            dumps = int(dumps)
            status = "CRITICAL" if dumps > 5 else ("WARNING" if dumps > 0 else "OK")
            metrics.append({
                "name": "ABAP Short Dumps (ST22)",
                "display_value": f"{dumps} dump(s)",
                "status": status,
                "detail": "Runtime exceptions"
            })
        except Exception:
            pass

    # 9. SP01 - Spool System
    sp01_extra = evidence_map.get("SP01", {}).get("extra", {})
    spools = sp01_extra.get("spool_count_visible")
    if spools is not None:
        metrics.append({
            "name": "Spool Requests (SP01)",
            "display_value": f"{spools} request(s)",
            "status": "OK",
            "detail": "Print/spool output jobs"
        })

    return metrics


def save_snapshot(result, gui_results: list = None, system_name: str = None):
    name = system_name or getattr(result, "system", "TST")
    path = _snapshot_path(name)

    # 1. Parse GUI Evidence for this specific system
    gui_evidence = []
    if gui_results:
        for m in gui_results:
            gui_evidence.append({
                "tcode": getattr(m, "tcode", None) or (m.get("tcode") if isinstance(m, dict) else ""),
                "display_value": getattr(m, "display_value", None) or (m.get("display_value") if isinstance(m, dict) else ""),
                "extra_data": getattr(m, "extra_data", {}) or (m.get("extra_data") if isinstance(m, dict) else {}),
            })

    # 2. Build Metrics dynamically per system
    metrics_data = _build_metrics_from_gui(gui_evidence, name)

    # 3. Derive Overall Status & Alerts for this system
    criticals = sum(1 for m in metrics_data if m.get("status") == "CRITICAL")
    warnings = sum(1 for m in metrics_data if m.get("status") == "WARNING")

    if criticals > 0:
        overall_status = "CRITICAL"
    elif warnings > 0:
        overall_status = "WARNING"
    else:
        overall_status = "HEALTHY"

    cycle_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    data = {
        "system": name,
        "client": getattr(result, "client", "000"),
        "cycle_timestamp": cycle_time_str,
        "overall_status": overall_status,
        "metrics": metrics_data,
        "ai_analysis": {
            "severity": "NORMAL" if overall_status == "HEALTHY" else overall_status,
            "root_cause": f"System {name} evidence verified. {len(metrics_data)} parameters checked, {criticals + warnings} alert(s) found.",
            "confidence": "HIGH",
        },
        "gui_evidence": gui_evidence,
        "generated_at": cycle_time_str,
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log.info(f"Status snapshot saved independently for {name}: {path}")
    except Exception as e:
        log.error(f"Failed to save status snapshot for {name}: {e}")


def load_snapshot(system_name: str) -> dict:
    path = _snapshot_path(system_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_snapshot_systems() -> list[str]:
    if not os.path.isdir(SNAPSHOT_DIR):
        return []
    return [f[:-5] for f in os.listdir(SNAPSHOT_DIR) if f.endswith(".json")]