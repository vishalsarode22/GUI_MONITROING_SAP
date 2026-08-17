"""
Fully automates launching SAP Logon and opening connection entries.
Supports direct COM OpenConnection (background-safe) and pywinauto fallback.
"""

import os
import subprocess
import time
import win32gui
import win32con
import pythoncom
import win32com.client

from pywinauto import Desktop
from pywinauto.application import Application
from utils.logger import get_logger

log = get_logger(__name__, "application")


def _hide_window_offscreen(hwnd: int):
    """Positions window off-screen to avoid stealing desktop focus."""
    try:
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_BOTTOM, -32000, -32000, 800, 600,
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
        )
    except Exception as e:
        log.debug(f"Window move note: {e}")


def kill_sap_processes():
    """Kills leftover SAP processes to ensure clean session state."""
    for proc in ["saplogon.exe", "sapgui.exe"]:
        try:
            subprocess.run(["taskkill", "/F", "/IM", proc], capture_output=True)
        except Exception as e:
            log.debug(f"taskkill {proc} skipped: {e}")
    time.sleep(1)


def launch_saplogon(exe_path: str, background: bool = False):
    """
    Launches SAP Logon.
    """
    log.info(f"Launching SAP Logon: {exe_path} (background={background})")
    startupinfo = None
    if background and os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = win32con.SW_SHOWMINNOACTIVE

    subprocess.Popen([exe_path], startupinfo=startupinfo)
    time.sleep(3)

    if background:
        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd) or ""
                if "SAP Logon" in title:
                    _hide_window_offscreen(hwnd)
        try:
            win32gui.EnumWindows(enum_cb, None)
        except Exception:
            pass


def select_connection(connection_name: str, timeout: int = 12, background: bool = False) -> bool:
    """
    Connects to the named system.
    Method 1: Native COM engine.OpenConnection (works silently in background).
    Method 2: Pywinauto UI item selection fallback.
    """
    log.info(f"Connecting to SAP system: '{connection_name}' (background={background})")
    
    # 1. Primary Method: Native SAP GUI Scripting OpenConnection (Headless/Background Safe)
    try:
        pythoncom.CoInitialize()
        time.sleep(1.5)
        sap_gui_auto = win32com.client.GetObject("SAPGUI")
        if sap_gui_auto:
            app = sap_gui_auto.GetScriptingEngine
            if app:
                # OpenConnection opens the named connection directly from the pad
                conn = app.OpenConnection(connection_name, True)
                if conn:
                    log.info(f"Successfully opened connection '{connection_name}' via SAP Scripting Engine.")
                    time.sleep(2)
                    return True
    except Exception as ex_com:
        log.debug(f"Native COM OpenConnection note: {ex_com}")

    # 2. Fallback Method: Pywinauto UI Selection
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            desktop = Desktop(backend="win32")
            sap_windows = [w for w in desktop.windows() if "SAP Logon" in (w.window_text() or "")]
            if sap_windows:
                logon_win = sap_windows[0]
                hwnd = logon_win.handle

                if background:
                    _hide_window_offscreen(hwnd)
                else:
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        logon_win.set_focus()
                    except Exception:
                        pass

                # Try SysListView32 list
                list_ctrl = logon_win.child_window(class_name="SysListView32")
                if list_ctrl.exists():
                    item = list_ctrl.get_item(connection_name)
                    item.click_input()
                    logon_win.type_keys("{ENTER}")
                    log.info(f"Selected connection '{connection_name}' via ListView.")
                    time.sleep(2)
                    return True

                # Try UIA backend
                app_uia = Application(backend="uia").connect(handle=hwnd)
                wnd_uia = app_uia.window(handle=hwnd)
                item = wnd_uia.child_window(title=connection_name, control_type="ListItem")
                if item.exists():
                    item.double_click_input()
                    log.info(f"Double-clicked connection '{connection_name}' via UIA.")
                    time.sleep(2)
                    return True
        except Exception as e:
            log.debug(f"UI selection retry: {e}")

        time.sleep(1)

    raise TimeoutError(
        f"Could not find/select connection '{connection_name}' in SAP Logon Pad. "
        f"Verify that '{connection_name}' matches the entry description in SAP Logon."
    )