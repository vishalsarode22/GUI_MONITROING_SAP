"""
SAP GUI Connection and Native Authentication Handler.
Handles Client, Username, and Password fields deterministically.
"""

import time
import win32gui
import win32con
from pywinauto import Desktop
from sap_gui.scripting_connection import get_scripting_session
from utils.logger import get_logger

log = get_logger(__name__, "connection")


def _dismiss_popups(session):
    """Dismisses License, Multi-logon, Copyright, or System Messages popups."""
    for _ in range(3):
        try:
            if session and session.Children.Count > 1:
                active_wnd = session.ActiveWindow
                if active_wnd and getattr(active_wnd, "Type", "") == "GuiModalWindow":
                    wnd_text = getattr(active_wnd, "Text", "")
                    log.info(f"Dismissing modal popup: '{wnd_text}'")

                    for opt_id in ["usr/radMULTI_LOGON_OPT2", "usr/radMULTI_LOGON_OPT1"]:
                        try:
                            opt = active_wnd.findById(opt_id, False)
                            if opt:
                                opt.select()
                                log.info(f"Selected multi-logon radio: {opt_id}")
                                break
                        except Exception:
                            continue

                    try:
                        active_wnd.sendVKey(0)
                    except Exception:
                        try:
                            btn = active_wnd.findById("tbar[0]/btn[0]", False)
                            if btn:
                                btn.press()
                        except Exception:
                            pass
                    time.sleep(1.2)
        except Exception as e:
            log.debug(f"Popup dismiss note: {e}")
            break


def login_native(client: str, username: str, password: str, language: str = "EN",
                 is_manual: bool = True, *args, **kwargs) -> dict:
    """
    Fills client, username, password, language and submits login into SAP GUI.
    """
    if not password:
        log.error("Login aborted: Password is empty. Check systems.yaml.")
        return {"success": False, "error": "Password is empty."}

    log.info(f"Submitting credentials -> Client: {client} | User: {username}")

    session = None
    # 1. Primary: Direct Scripting API binding
    for attempt in range(1, 8):
        try:
            session = get_scripting_session(timeout=4)
            if session:
                wnd = session.findById("wnd[0]", False)
                if wnd:
                    # Set Client
                    client_field = session.findById("wnd[0]/usr/txtRSYST-MANDT", False)
                    if client_field:
                        client_field.text = str(client).strip()

                    # Set Username
                    user_field = session.findById("wnd[0]/usr/txtRSYST-BNAME", False)
                    if user_field:
                        user_field.text = str(username).strip()

                    # Set Password
                    pwd_field = session.findById("wnd[0]/usr/pwdRSYST-BCODE", False)
                    if pwd_field:
                        pwd_field.text = str(password).strip()

                    # Set Language
                    lang_field = session.findById("wnd[0]/usr/txtRSYST-LANGU", False)
                    if lang_field:
                        lang_field.text = str(language or "EN").strip()

                    time.sleep(0.4)

                    # Press Enter / sendVKey 0
                    session.findById("wnd[0]").sendVKey(0)
                    time.sleep(2.5)

                    # Clear popups
                    _dismiss_popups(session)

                    # Check statusbar errors
                    try:
                        sbar = session.findById("wnd[0]/sbar", False)
                        if sbar and getattr(sbar, "Text", ""):
                            msg_type = getattr(sbar, "MessageType", "")
                            if msg_type in ["E", "A"]:
                                log.error(f"SAP Logon rejected: {sbar.Text}")
                                return {"success": False, "error": sbar.Text}
                    except Exception:
                        pass

                    log.info("SAP GUI authentication verified successfully.")
                    return {"success": True, "session": session}

        except Exception as ex:
            log.debug(f"Logon attempt {attempt} retry: {ex}")
            time.sleep(1)

    # 2. Pywinauto Fallback
    log.info("Attempting pywinauto keyboard fallback logon...")
    try:
        desktop = Desktop(backend="win32")
        sap_windows = [w for w in desktop.windows() if "SAP" in (w.window_text() or "")]
        if sap_windows:
            win = sap_windows[0]
            if is_manual:
                try:
                    win.set_focus()
                except Exception:
                    pass

            win.type_keys(f"{client}{{TAB}}{username}{{TAB}}{password}{{TAB}}{language}{{ENTER}}", pause=0.05)
            time.sleep(3)

            session = get_scripting_session(timeout=3)
            if session:
                _dismiss_popups(session)
                return {"success": True, "session": session}
    except Exception as ex_fallback:
        log.error(f"Fallback keyboard login failed: {ex_fallback}")

    return {"success": False, "error": "Could not authenticate into SAP GUI."}


login = login_native