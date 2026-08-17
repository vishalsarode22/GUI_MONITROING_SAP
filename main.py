"""
Master pipeline: sequences the entire SAP BASIS monitoring cycle end to end.
Thread-safe execution guarded by an atomic mutex lock.
"""

import sys
import time
import subprocess
import os
import threading

from core.config_loader import (
    get_sap_credentials, get_launch_config, get_monitoring_tasks,
    get_smtp_config, get_systems,
)
from sap_gui.launcher import kill_sap_processes, launch_saplogon, select_connection
from sap_gui.connection import login
from sap_gui.scripting_connection import get_active_session, get_scripting_session
from core.orchestrator import run_monitoring_cycle
from collectors.sap_gui_collector import collect_tcode_evidence
from reporting.excel_writer import append_result_to_excel
from reporting.excel_template_writer import fill_metrobrands_template
from notifications.email_report import send_final_report
from core.status_snapshot import save_snapshot
from utils.logger import get_logger

log = get_logger(__name__, "application")

TEMPLATE_PATH = "config/templates/MetroBrands_template.xlsx"
_PIPELINE_LOCK = threading.Lock()


def close_sap_gui(session=None):
    """Closes SAP GUI session cleanly."""
    log.info("Closing SAP GUI and SAP Logon sessions...")
    try:
        if session:
            try:
                session.findById("wnd[0]").close()
                if session.Children.Count > 0:
                    session.ActiveWindow.sendVKey(0)
            except Exception:
                pass

        subprocess.run(["taskkill", "/F", "/IM", "sapgui.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["taskkill", "/F", "/IM", "saplogon.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.info("SAP sessions closed successfully.")
    except Exception as e:
        log.warning(f"Could not close SAP GUI automatically: {e}")


def safe_generate_pdf_report(result, gui_results):
    """Generates PDF using LaTeX builder with fallback to native Python builder."""
    pdf_path = None
    try:
        from reporting.latex_report_builder import generate_latex_pdf_report
        pdf_path = generate_latex_pdf_report(result, gui_results=gui_results)
    except Exception as e:
        log.warning(f"LaTeX PDF generation failed ({e}), falling back to native Python PDF builder...")
        try:
            import reporting.pdf_builder as pb
            if hasattr(pb, "generate_pdf_report"):
                pdf_path = pb.generate_pdf_report(result, gui_results=gui_results)
            elif hasattr(pb, "build_pdf_report"):
                pdf_path = pb.build_pdf_report(result, gui_results=gui_results)
            elif hasattr(pb, "create_pdf"):
                pdf_path = pb.create_pdf(result, gui_results=gui_results)
        except Exception as e_inner:
            log.error(f"Native PDF builder also failed: {e_inner}. Skipping PDF generation.")
            pdf_path = None
    return pdf_path


def run_pipeline_for_system(system_config: dict, is_manual: bool = False) -> bool:
    """
    Runs monitoring pipeline guarded by a mutex lock to avoid duplicate collisions.
    """
    if not _PIPELINE_LOCK.acquire(blocking=False):
        log.warning("Monitoring pipeline is already actively running. Ignoring duplicate trigger request.")
        return False

    name = system_config.get("id", system_config.get("name", "TST"))
    connection_name = system_config.get("connection_name", system_config.get("name", "test system"))
    client = system_config.get("client", "000")
    username = system_config.get("username", "EMI")
    password = system_config.get("password", "")
    language = system_config.get("language", "EN")
    background = not is_manual

    log.info(f"===== Pipeline START for system {name} ({connection_name}) | is_manual={is_manual} =====")

    ssh_host = system_config.get("ssh_host", "").strip()
    if ssh_host:
        ssh_creds = {
            "host": ssh_host,
            "port": system_config.get("ssh_port", 22),
            "username": system_config.get("ssh_username", ""),
            "password": system_config.get("ssh_password", ""),
        }
    else:
        ssh_creds = {"host": ""}

    gui_available = True
    session = None

    try:
        kill_sap_processes()
        launch_saplogon(get_launch_config()["exe_path"], background=background)
        select_connection(connection_name, background=background)
        time.sleep(2)

        login_result = login(
            client=client,
            username=username,
            password=password,
            language=language,
            is_manual=is_manual
        )
        if not login_result.get("success", False):
            log.warning(f"Login failed for {name}: {login_result.get('error')} -- continuing with OS-only monitoring.")
            gui_available = False
        else:
            session = login_result.get("session") or get_active_session() or get_scripting_session()
            if session is None:
                log.warning(f"Could not acquire scripting session for {name} -- continuing with OS-only monitoring.")
                gui_available = False

        # OS metrics
        result = run_monitoring_cycle(system=name, client=client, ssh_creds=ssh_creds)

        # Evidence collection
        gui_results = []
        if gui_available:
            time.sleep(3)  # Post-logon stabilization
            tasks = get_monitoring_tasks()
            gui_results = collect_tcode_evidence(tasks)
        else:
            log.info(f"Skipping T-code GUI evidence for {name} -- no active SAP session.")

        save_snapshot(result, gui_results=gui_results, system_name=name)

        pdf_path = safe_generate_pdf_report(result, gui_results=gui_results)
        excel_history_path = append_result_to_excel(result)

        metrobrands_path = None
        if os.path.exists(TEMPLATE_PATH):
            try:
                date_str = time.strftime('%Y-%m-%d')
                os.makedirs(f"reports/{date_str}", exist_ok=True)
                metrobrands_path = fill_metrobrands_template(
                    template_path=TEMPLATE_PATH,
                    output_path=f"reports/{date_str}/{name}_Monitoring Sheet.xlsx",
                    gui_results=gui_results,
                )
            except Exception as e:
                log.warning(f"Failed to fill Excel template for {name}: {e}")

        try:
            smtp_config = get_smtp_config()
            send_final_report(result, smtp_config, pdf_path, metrobrands_path)
        except Exception as e:
            log.warning(f"Email delivery skipped or failed for {name}: {e}")

        log.info(f"===== Pipeline COMPLETE for system {name} (gui_available={gui_available}) =====")
        return True

    finally:
        close_sap_gui(session)
        _PIPELINE_LOCK.release()


def run_full_pipeline(system: str = "TST", client: str = "000", background: bool = False):
    creds = get_sap_credentials()
    sys_cfg = {
        "id": system,
        "name": system,
        "connection_name": get_launch_config().get("connection_name", "test system"),
        "client": client,
        "username": creds.get("username", "EMI"),
        "password": creds.get("password", ""),
        "language": creds.get("language", "EN")
    }
    return run_pipeline_for_system(sys_cfg, is_manual=(not background))


if __name__ == "__main__":
    run_full_pipeline(system="TST", client="000", background=False)