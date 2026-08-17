"""
Captures SAP GUI transaction screenshots cleanly.
Ensures post-logon transition and UI rendering before capturing.
"""

import os
import time
import win32gui
import win32con
from PIL import ImageGrab
from utils.logger import get_logger

log = get_logger(__name__, "screenshot")


def wait_for_screen_ready(session, timeout: float = 6.0):
    """Waits for SAP window to finish rendering data before screenshot."""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            if session and not getattr(session, "Busy", False):
                wnd = session.findById("wnd[0]", False)
                if wnd and not getattr(wnd, "Busy", False):
                    break
        except Exception:
            pass
        time.sleep(0.3)
    time.sleep(0.5)


def capture_screenshot(session, filepath_or_name: str) -> str:
    """
    Captures screenshot of the current SAP transaction screen.
    """
    if not filepath_or_name.endswith(".png"):
        date_str = time.strftime("%Y-%m-%d")
        dir_path = os.path.join("reports", date_str, "screenshots")
        os.makedirs(dir_path, exist_ok=True)
        filepath = os.path.join(dir_path, f"{filepath_or_name}_{time.strftime('%H%M%S')}.png")
    else:
        filepath = filepath_or_name
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Wait for transaction screen transition
    wait_for_screen_ready(session)

    # 1. Primary: SAP Scripting Engine Native hardCopy
    try:
        if session and hasattr(session, "Children") and session.Children.Count > 0:
            active_wnd = getattr(session, "ActiveWindow", None) or session.findById("wnd[0]", False)
            if active_wnd:
                # Discard hardCopy if still showing RSYST logon screen
                if "RSYST" not in getattr(active_wnd, "Name", ""):
                    active_wnd.hardCopy(filepath, 1)
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 2000:
                        log.info(f"Screenshot saved: {filepath}")
                        return filepath
    except Exception as ex_hardcopy:
        log.debug(f"hardCopy note: {ex_hardcopy}")

    # 2. Fallback: OS-level Window Capture
    try:
        hwnd = None
        def enum_cb(h, _):
            nonlocal hwnd
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h) or ""
                if "SAP" in title and "SAP Logon" not in title:
                    hwnd = h
        win32gui.EnumWindows(enum_cb, None)

        if hwnd:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
            rect = win32gui.GetWindowRect(hwnd)
            img = ImageGrab.grab(bbox=rect)
            img.save(filepath)
            log.info(f"Screenshot saved (fallback): {filepath}")
            return filepath
    except Exception as ex_grab:
        log.error(f"Failed to capture screenshot: {ex_grab}")

    return None