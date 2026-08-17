"""
Dynamic SAP BASIS Monitoring Desktop Dashboard.
Handles multi-system switching, live snapshot loading, GUI system registration,
and per-system monitoring runs.
"""

import os
import sys
import yaml
import json
import threading
import webview

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config_loader import get_systems
from core.status_snapshot import load_snapshot, list_snapshot_systems
from main import run_pipeline_for_system
from utils.logger import get_logger

log = get_logger(__name__, "dashboard")
SYSTEMS_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "systems.yaml")


class DashboardAPI:
    """JavaScript API bridge exposed to the webview frontend."""

    def get_configured_systems(self):
        """Returns all configured systems from config/systems.yaml."""
        try:
            if not os.path.exists(SYSTEMS_CONFIG_PATH):
                return []
            with open(SYSTEMS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            systems = data.get("systems", [])
            return systems
        except Exception as e:
            log.error(f"Failed to read systems.yaml: {e}")
            return []

    def get_system_status(self, system_id: str):
        """Loads and returns the snapshot JSON for the requested system."""
        try:
            snapshot = load_snapshot(system_id)
            if not snapshot:
                # Return empty template for a freshly added or unmonitored system
                return {
                    "system": system_id,
                    "client": "---",
                    "cycle_timestamp": "Not yet monitored",
                    "overall_status": "NOT_MONITORED",
                    "metrics": [],
                    "ai_analysis": {
                        "severity": "INFO",
                        "root_cause": f"System '{system_id}' has not been monitored yet. Click 'Run Monitoring' to start.",
                        "confidence": "HIGH",
                    },
                    "gui_evidence": [],
                }
            return snapshot
        except Exception as e:
            log.error(f"Error loading snapshot for {system_id}: {e}")
            return None

    def add_system(self, system_data: dict):
        """Adds a new system from the GUI form into config/systems.yaml."""
        try:
            sys_id = (system_data.get("name") or system_data.get("id") or "SYS").strip().upper()
            client = str(system_data.get("client") or "000").strip()
            connection_name = system_data.get("connection_name", "").strip()
            username = system_data.get("username", "").strip()
            password = system_data.get("password", "").strip()

            if not connection_name:
                return {"success": False, "error": "Connection name is required."}

            os.makedirs(os.path.dirname(SYSTEMS_CONFIG_PATH), exist_ok=True)
            current_data = {"systems": []}
            if os.path.exists(SYSTEMS_CONFIG_PATH):
                with open(SYSTEMS_CONFIG_PATH, "r", encoding="utf-8") as f:
                    current_data = yaml.safe_load(f) or {"systems": []}

            # Avoid duplicates by updating existing or appending new
            systems_list = current_data.get("systems", [])
            existing = next((s for s in systems_list if s.get("id", "").upper() == sys_id), None)
            
            new_entry = {
                "id": sys_id,
                "name": sys_id,
                "description": f"SAP System {sys_id}",
                "connection_name": connection_name,
                "client": client,
                "username": username,
                "password": password,
                "language": "EN",
                "enabled": True
            }

            if existing:
                existing.update(new_entry)
            else:
                systems_list.append(new_entry)

            current_data["systems"] = systems_list
            with open(SYSTEMS_CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(current_data, f, sort_keys=False)

            log.info(f"System '{sys_id}' successfully added/updated in systems.yaml.")
            return {"success": True, "system": new_entry}
        except Exception as e:
            log.error(f"Failed to add system: {e}")
            return {"success": False, "error": str(e)}

    def run_monitoring_for_system(self, system_id: str):
        """Runs the monitoring pipeline in the background for the selected system."""
        systems = self.get_configured_systems()
        target_sys = next((s for s in systems if s.get("id", "").upper() == system_id.upper() or s.get("name", "").upper() == system_id.upper()), None)

        if not target_sys:
            return {"success": False, "error": f"System configuration for '{system_id}' not found."}

        def _worker():
            try:
                log.info(f"Manual monitoring triggered for: {system_id}")
                run_pipeline_for_system(target_sys)
            except Exception as e:
                log.error(f"Monitoring failed for {system_id}: {e}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return {"success": True, "message": f"Monitoring started for {system_id}."}


def start_dashboard():
    api = DashboardAPI()
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
    
    window = webview.create_window(
        title="SAP BASIS Monitoring Dashboard",
        url=html_path,
        js_api=api,
        width=1320,
        height=860,
        min_size=(1024, 700)
    )
    webview.start(debug=False)


if __name__ == "__main__":
    start_dashboard()