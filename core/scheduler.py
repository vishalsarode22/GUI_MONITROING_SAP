"""
Automated background scheduler for SAP BASIS Monitoring.
Supports fixed daily times (e.g. '11:00') or recurring intervals (e.g. every 2 hours).
"""

import time
import threading
import schedule
import yaml
import os

from main import run_pipeline_for_system
from utils.logger import get_logger

log = get_logger(__name__, "scheduler")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "systems.yaml")

_scheduler_thread = None
_stop_event = threading.Event()


def get_all_enabled_systems() -> list:
    """Reads all active systems from config/systems.yaml."""
    if not os.path.exists(CONFIG_PATH):
        return []
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return [s for s in data.get("systems", []) if s.get("enabled", True)]
    except Exception as e:
        log.error(f"Error loading systems: {e}")
        return []


def run_scheduled_job():
    """Runs monitoring sequentially for every configured system."""
    systems = get_all_enabled_systems()
    log.info(f"--- [SCHEDULED RUN] Starting automatic cycle for {len(systems)} system(s) ---")
    
    for sys_cfg in systems:
        sys_name = sys_cfg.get("id", sys_cfg.get("name", "SYS"))
        try:
            log.info(f"Scheduler: Executing background run for {sys_name}...")
            # is_manual=False keeps it in background mode
            run_pipeline_for_system(sys_cfg, is_manual=False)
        except Exception as e:
            log.error(f"Scheduler failed for system {sys_name}: {e}")

    log.info("--- [SCHEDULED RUN] Cycle completed for all systems ---")


def _scheduler_loop():
    """Background worker loop checking for due jobs."""
    while not _stop_event.is_set():
        schedule.run_pending()
        time.sleep(1)


def configure_schedule(mode: str = "interval", value: str = "120"):
    """
    Configures the monitoring schedule.
    :param mode: 'interval' (in hours or minutes) or 'daily' (fixed time like '11:00')
    :param value: e.g., '120' (for every 2 hours / 120 mins) or '11:00' (daily at 11:00 AM)
    """
    global _scheduler_thread, _stop_event
    
    schedule.clear()
    _stop_event.clear()

    if mode == "daily":
        # Example: daily at 11:00 AM (24-hour format: "11:00")
        schedule.every().day.at(value).do(run_scheduled_job)
        log.info(f"Scheduler set: Daily at {value}")

    elif mode == "hours":
        # Example: every 2 hours
        hrs = max(1, int(value))
        schedule.every(hrs).hours.do(run_scheduled_job)
        log.info(f"Scheduler set: Every {hrs} hour(s)")

    elif mode == "minutes":
        # Example: every 15 or 30 minutes
        mins = max(1, int(value))
        schedule.every(mins).minutes.do(run_scheduled_job)
        log.info(f"Scheduler set: Every {mins} minute(s)")

    if _scheduler_thread is None or not _scheduler_thread.is_alive():
        _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
        _scheduler_thread.start()


def stop_scheduler():
    global _stop_event
    _stop_event.set()
    schedule.clear()
    log.info("Scheduler stopped.")