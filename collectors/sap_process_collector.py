"""
SAP work process monitoring via sapcontrol.
Runs sapcontrol -nr <instance> -function GetProcessList over SSH on the SAP host.
Reuses the same SSH connection approach as linux_collector.py.
"""

import paramiko

from utils.logger import get_logger
from core.models import MetricResult, Status

log = get_logger(__name__, "monitoring")


def _connect(host: str, port: int, username: str, password: str, timeout: int = 10) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=username, password=password, timeout=timeout)
    return client


def _run(client: paramiko.SSHClient, command: str) -> str:
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if err:
        log.debug(f"Command produced stderr: {command} -> {err}")
    return out


def collect_sap_process_list(host: str, port: int, username: str, password: str,
                              instance_nr: str) -> dict:
    """
    Returns raw sapcontrol GetProcessList output.
    On failure, returns {"error": "..."} so orchestrator can continue.
    """
    try:
        client = _connect(host, port, username, password)
    except Exception as e:
        log.error(f"SSH connection failed (sap_process_collector): {e}")
        return {"error": str(e)}

    try:
        raw = _run(client, f"sapcontrol -nr {instance_nr} -function GetProcessList")
        log.info("SAP process list collected successfully.")
        return {"raw": raw}
    except Exception as e:
        log.error(f"Error collecting SAP process list: {e}")
        return {"error": str(e)}
    finally:
        client.close()


def parse_sap_process_list(raw_result: dict) -> list[MetricResult]:
    """
    Parses sapcontrol's CSV-style output into MetricResult objects.
    Expected format:
        name, description, dispstatus, textstatus, starttime, elapsedtime, pid
        disp+work, Dispatcher, GREEN, Running, ...
    Status mapping: GREEN -> NORMAL, YELLOW -> WARNING, RED -> CRITICAL, GRAY -> UNKNOWN
    """
    results = []

    if "error" in raw_result:
        log.error(f"Skipping parse -- collector reported error: {raw_result['error']}")
        return results

    raw = raw_result.get("raw", "")
    lines = raw.splitlines()

    status_map = {
        "GREEN": Status.NORMAL,
        "YELLOW": Status.WARNING,
        "RED": Status.CRITICAL,
        "GRAY": Status.UNKNOWN,
    }

    # Find the header line, then parse everything after it
    header_index = None
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("name,"):
            header_index = i
            break

    if header_index is None:
        log.error("Could not find header line in sapcontrol output -- unexpected format.")
        return results

    for line in lines[header_index + 1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        process_name = parts[0]
        dispstatus = parts[2].upper()
        textstatus = parts[3]

        status = status_map.get(dispstatus, Status.UNKNOWN)

        results.append(MetricResult(
            name=f"sap_process_{process_name}",
            value=None,
            display_value=dispstatus,
            status=status,
            source="sap_process_collector",
            detail=f"{process_name}: {textstatus}"
        ))

    log.info(f"Parsed {len(results)} SAP process statuses.")
    return results