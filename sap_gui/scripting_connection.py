"""
SAP GUI Scripting connection helper.
Provides a reliable, deterministic way to get the active SAP session
for navigation and field data extraction, with full background thread safety.
"""

import time
import pythoncom
import win32com.client
from utils.logger import get_logger

log = get_logger(__name__, "scripting_connection")


def get_scripting_engine():
    """Acquires the top-level SAP GUI Scripting Engine COM object."""
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        sap_gui_auto = win32com.client.GetObject("SAPGUI")
        if sap_gui_auto:
            application = sap_gui_auto.GetScriptingEngine
            if application:
                return application
    except Exception as ex_direct:
        log.debug(f"Direct ROT lookup note: {ex_direct}")

    try:
        rot_wrapper = win32com.client.Dispatch("SapROTWr.SapROTWrapper")
        sap_gui_auto = rot_wrapper.GetROTEntry("SAPGUI")
        if sap_gui_auto:
            application = sap_gui_auto.GetScriptingEngine
            if application:
                return application
    except Exception as ex_wrapper:
        log.debug(f"SapROTWrapper lookup note: {ex_wrapper}")

    return None


def handle_initial_popups(session):
    """Dismisses standard post-logon modal popups."""
    try:
        if session and hasattr(session, "Children") and session.Children.Count > 1:
            active_window = getattr(session, "ActiveWindow", None)
            if active_window and getattr(active_window, "Type", "") == "GuiModalWindow":
                wnd_text = getattr(active_window, "Text", "")
                log.info(f"Handling modal popup: '{wnd_text}'")

                for opt_id in ["usr/radMULTI_LOGON_OPT2", "usr/radMULTI_LOGON_OPT1"]:
                    try:
                        opt = active_window.findById(opt_id, False)
                        if opt:
                            opt.select()
                            log.info(f"Selected logon radio option: {opt_id}")
                            break
                    except Exception:
                        continue

                try:
                    active_window.sendVKey(0)
                    time.sleep(1.5)
                except Exception:
                    pass
    except Exception as e:
        log.debug(f"Popup check note: {e}")


def get_scripting_session(max_retries: int = 10, retry_delay: float = 1.0, timeout: float = None, *args, **kwargs):
    """
    Finds and returns the active SAP GUI session object (GuiSession).
    Accepts both max_retries and timeout kwargs to prevent TypeErrors.
    """
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    if timeout is not None:
        max_retries = max(1, int(timeout / max(retry_delay, 0.5)))

    for attempt in range(1, max_retries + 1):
        app = get_scripting_engine()
        if not app:
            time.sleep(retry_delay)
            continue

        try:
            conn_count = app.Children.Count
        except Exception:
            conn_count = 0

        if conn_count == 0:
            time.sleep(retry_delay)
            continue

        for c_idx in range(conn_count):
            try:
                connection = app.Children(c_idx)
                if connection and connection.Children.Count > 0:
                    for s_idx in range(connection.Children.Count):
                        session = connection.Children(s_idx)
                        if session:
                            handle_initial_popups(session)
                            return session
            except Exception as ex_sess:
                log.debug(f"Session inspection note (Connection {c_idx}): {ex_sess}")

        time.sleep(retry_delay)

    return None


get_active_session = get_scripting_session