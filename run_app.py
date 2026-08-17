"""
Desktop Controller for SAP BASIS AI Monitor.
Clean background thread isolation without desktop-blocking loops.
"""

import os
import sys
import yaml
import threading
import time
import pythoncom
from datetime import datetime
import webview

try:
    import schedule
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.status_snapshot import load_snapshot
from core.security_vault import save_credential, get_credential
from main import run_pipeline_for_system
from utils.logger import get_logger

log = get_logger(__name__, "desktop_app")
SYSTEMS_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "systems.yaml")
EMAIL_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "email_config.yaml")
SCHEDULES_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "schedules.yaml")

_scheduler_thread = None
_stop_event = threading.Event()

_telemetry = {
    "is_running": False,
    "current_system": None,
    "current_activity": "Idle (Standing by)",
    "last_run_timestamp": "Not yet run"
}

def _get_system_config(system_id: str) -> dict:
    """
    Reads system configuration. Uses YAML password first,
    falling back to Windows Credential Vault if available.
    """
    if not os.path.exists(SYSTEMS_CONFIG_PATH):
        return None
    try:
        with open(SYSTEMS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for s in data.get("systems", []):
            if s.get("id", "").upper() == system_id.upper() or s.get("name", "").upper() == system_id.upper():
                sys_id = s.get("id", s.get("name", ""))
                # If YAML has no password or it is masked, fetch from Windows Vault
                if not s.get("password") or s.get("password") == "******":
                    vault_pwd = get_credential(f"SAP_PWD_{sys_id}")
                    if vault_pwd:
                        s["password"] = vault_pwd
                return s
    except Exception as e:
        log.error(f"Error loading system {system_id}: {e}")
    return None

def _run_background_job_for_system(system_id: str):
    """Executes scheduled monitoring cleanly in a background thread."""
    global _telemetry
    pythoncom.CoInitialize()

    sys_cfg = _get_system_config(system_id)
    if not sys_cfg:
        log.warning(f"Scheduler skipped {system_id}: Config not found.")
        return

    _telemetry["is_running"] = True
    _telemetry["current_system"] = system_id
    _telemetry["current_activity"] = f"Background monitoring cycle running for {system_id}..."

    try:
        log.info(f"--- [SCHEDULED BACKGROUND RUN: {system_id}] Starting ---")
        run_pipeline_for_system(sys_cfg, is_manual=False)
        _telemetry["last_run_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _telemetry["current_activity"] = f"Completed background run for {system_id}."
    except Exception as e:
        log.error(f"Background run failed for {system_id}: {e}")
        _telemetry["current_activity"] = f"Failed for {system_id}: {e}"
    finally:
        _telemetry["is_running"] = False
        _telemetry["current_system"] = None


def _scheduler_loop():
    while not _stop_event.is_set():
        if HAS_SCHEDULE:
            schedule.run_pending()
        time.sleep(1)


class DesktopAPI:
    def __init__(self):
        self._load_and_apply_all_schedules()

    def _load_and_apply_all_schedules(self):
        global _scheduler_thread, _stop_event
        if not HAS_SCHEDULE or not os.path.exists(SCHEDULES_CONFIG_PATH):
            return
        try:
            with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = yaml.safe_load(f) or {}

            schedule.clear()
            for sys_id, conf in saved.items():
                mode = conf.get("mode")
                val = conf.get("value")
                if not mode or not val:
                    continue

                if mode == "minutes":
                    schedule.every(max(1, int(val))).minutes.do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)
                elif mode == "hours":
                    schedule.every(max(1, int(val))).hours.do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)
                elif mode == "daily":
                    schedule.every().day.at(val).do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)

            if (_scheduler_thread is None or not _scheduler_thread.is_alive()) and schedule.get_jobs():
                _stop_event.clear()
                _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
                _scheduler_thread.start()
        except Exception as e:
            log.error(f"Failed to load schedules: {e}")

    def get_system_schedule(self, system_id: str):
        sys_id = system_id.upper()
        res = {"mode": "minutes", "value": "5", "is_active": False, "next_run": "No schedule set"}

        if os.path.exists(SCHEDULES_CONFIG_PATH):
            try:
                with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f) or {}
                if sys_id in saved:
                    res["mode"] = saved[sys_id].get("mode", "minutes")
                    res["value"] = saved[sys_id].get("value", "5")
                    res["is_active"] = True
            except Exception:
                pass

        if HAS_SCHEDULE:
            matching_jobs = [j for j in schedule.get_jobs(sys_id)]
            if matching_jobs and hasattr(matching_jobs[0], 'next_run') and matching_jobs[0].next_run:
                next_dt = matching_jobs[0].next_run
                diff_sec = int((next_dt - datetime.now()).total_seconds())
                if diff_sec > 0:
                    mins, secs = divmod(diff_sec, 60)
                    res["next_run"] = f"{next_dt.strftime('%H:%M:%S')} (in {mins}m {secs}s)"
                else:
                    res["next_run"] = f"{next_dt.strftime('%H:%M:%S')} (Due now)"
                res["is_active"] = True

        return res

    def set_system_schedule(self, system_id: str, mode: str, value: str):
        global _scheduler_thread, _stop_event
        if not HAS_SCHEDULE:
            return {"success": False, "error": "schedule library missing"}

        sys_id = system_id.upper()
        try:
            schedule.clear(sys_id)

            if mode == "minutes":
                mins = max(1, int(value))
                schedule.every(mins).minutes.do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)
                msg = f"{sys_id} set to every {mins} min(s)"
            elif mode == "hours":
                hrs = max(1, int(value))
                schedule.every(hrs).hours.do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)
                msg = f"{sys_id} set to every {hrs} hour(s)"
            elif mode == "daily":
                schedule.every().day.at(value).do(_run_background_job_for_system, system_id=sys_id).tag(sys_id)
                msg = f"{sys_id} set daily at {value}"
            else:
                return {"success": False, "error": "Invalid mode"}

            os.makedirs(os.path.dirname(SCHEDULES_CONFIG_PATH), exist_ok=True)
            saved = {}
            if os.path.exists(SCHEDULES_CONFIG_PATH):
                with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f) or {}
            saved[sys_id] = {"mode": mode, "value": value}
            with open(SCHEDULES_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(saved, f, sort_keys=False)

            if _scheduler_thread is None or not _scheduler_thread.is_alive():
                _stop_event.clear()
                _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
                _scheduler_thread.start()

            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_system_schedule(self, system_id: str):
        sys_id = system_id.upper()
        if HAS_SCHEDULE:
            schedule.clear(sys_id)
        if os.path.exists(SCHEDULES_CONFIG_PATH):
            try:
                with open(SCHEDULES_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = yaml.safe_load(f) or {}
                if sys_id in saved:
                    del saved[sys_id]
                    with open(SCHEDULES_CONFIG_PATH, "w", encoding="utf-8") as f:
                        yaml.safe_dump(saved, f, sort_keys=False)
            except Exception:
                pass
        return {"success": True, "message": f"Schedule stopped for {sys_id}."}

    def get_scheduler_telemetry(self):
        global _telemetry
        return _telemetry

    def get_configured_systems(self):
        try:
            if not os.path.exists(SYSTEMS_CONFIG_PATH):
                return []
            with open(SYSTEMS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            systems = data.get("systems", [])
            for s in systems:
                s["password"] = "******"
            return systems
        except Exception:
            return []

    def get_system_status(self, system_id: str):
        try:
            snapshot = load_snapshot(system_id)
            if not snapshot:
                return {
                    "system": system_id,
                    "client": "---",
                    "cycle_timestamp": "Not yet monitored",
                    "overall_status": "NOT_MONITORED",
                    "metrics": [],
                    "ai_analysis": {
                        "severity": "INFO",
                        "root_cause": f"System '{system_id}' has not been monitored yet.",
                        "confidence": "HIGH",
                    },
                    "gui_evidence": [],
                }
            return snapshot
        except Exception:
            return None

    def add_system(self, system_data: dict):
        try:
            sys_id = (system_data.get("name") or system_data.get("id") or "SYS").strip().upper()
            client = str(system_data.get("client") or "000").strip()
            connection_name = system_data.get("connection_name", "").strip()
            username = system_data.get("username", "").strip()
            password = system_data.get("password", "").strip()

            if not connection_name:
                return {"success": False, "error": "Connection name is required."}

            if password:
                save_credential(f"SAP_PWD_{sys_id}", password)

            os.makedirs(os.path.dirname(SYSTEMS_CONFIG_PATH), exist_ok=True)
            current_data = {"systems": []}
            if os.path.exists(SYSTEMS_CONFIG_PATH):
                with open(SYSTEMS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    current_data = yaml.safe_load(f) or {"systems": []}

            systems_list = current_data.get("systems", [])
            existing = next((s for s in systems_list if s.get("id", "").upper() == sys_id), None)

            new_entry = {
                "id": sys_id,
                "name": sys_id,
                "description": f"SAP System {sys_id}",
                "connection_name": connection_name,
                "client": client,
                "username": username,
                "language": "EN",
                "enabled": True,
            }

            if existing:
                existing.update(new_entry)
            else:
                systems_list.append(new_entry)

            current_data["systems"] = systems_list
            with open(SYSTEMS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(current_data, f, sort_keys=False)

            return {"success": True, "system": new_entry}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_monitoring_for_system(self, system_id: str):
        global _telemetry
        sys_cfg = _get_system_config(system_id)
        if not sys_cfg:
            return {"success": False, "error": f"System '{system_id}' not found."}

        def _worker():
            global _telemetry
            pythoncom.CoInitialize()
            _telemetry["is_running"] = True
            _telemetry["current_system"] = system_id
            _telemetry["current_activity"] = f"Manual run on active screen for {system_id}..."
            try:
                run_pipeline_for_system(sys_cfg, is_manual=True)
                _telemetry["last_run_timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                _telemetry["current_activity"] = f"Completed monitoring for {system_id}."
            except Exception as e:
                _telemetry["current_activity"] = f"Failed for {system_id}: {e}"
            finally:
                _telemetry["is_running"] = False
                _telemetry["current_system"] = None

        threading.Thread(target=_worker, daemon=True).start()
        return {"success": True, "message": f"Monitoring running on screen for {system_id}."}

    def get_email_settings(self):
        if not os.path.exists(EMAIL_CONFIG_PATH):
            return {"active_sender": "", "saved_senders": [], "recipients": "", "cc_recipients": ""}
        try:
            with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return {
                "active_sender": data.get("sender_email", ""),
                "saved_senders": data.get("saved_senders_list", []),
                "recipients": data.get("recipients", ""),
                "cc_recipients": data.get("cc_recipients", "")
            }
        except Exception:
            return {}

    def save_email_settings(self, email_data: dict):
        try:
            sender = email_data.get("sender_email", "").strip()
            password = email_data.get("sender_password", "").strip()

            if password:
                save_credential(f"EMAIL_PWD_{sender}", password)

            os.makedirs(os.path.dirname(EMAIL_CONFIG_PATH), exist_ok=True)
            current_cfg = {}
            if os.path.exists(EMAIL_CONFIG_PATH):
                with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                    current_cfg = yaml.safe_load(f) or {}

            saved_list = current_cfg.get("saved_senders_list", [])
            if sender and sender not in saved_list:
                saved_list.append(sender)

            payload = {
                "sender_email": sender,
                "saved_senders_list": saved_list,
                "recipients": email_data.get("recipients", []),
                "cc_recipients": email_data.get("cc_recipients", [])
            }

            with open(EMAIL_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(payload, f, sort_keys=False)

            return {"success": True, "message": "Email settings saved successfully!"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def main():
    api = DesktopAPI()
    html_file = os.path.join(PROJECT_ROOT, "dashboard", "index.html")
    window = webview.create_window(
        title="SAP BASIS AI Monitoring Application",
        url=html_file,
        js_api=api,
        width=1280,
        height=800,
        min_size=(900, 600),
        resizable=True,
        maximized=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()