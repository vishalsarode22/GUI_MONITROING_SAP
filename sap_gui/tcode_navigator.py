"""
Robust SAP T-Code Navigator.
Uses native session.StartTransaction() for reliable screen transitions from any state.
"""

import time
from utils.logger import get_logger

log = get_logger(__name__, "tcode_navigator")


def dismiss_popups(session):
    """Dismisses unexpected modal dialogs that block transaction navigation."""
    try:
        if session and hasattr(session, "Children") and session.Children.Count > 1:
            active_wnd = getattr(session, "ActiveWindow", None)
            if active_wnd and getattr(active_wnd, "Type", "") == "GuiModalWindow":
                try:
                    active_wnd.sendVKey(0)  # Enter
                except Exception:
                    try:
                        active_wnd.sendVKey(12)  # F12 Cancel
                    except Exception:
                        pass
                time.sleep(0.5)
    except Exception:
        pass


def wait_until_not_busy(session, max_busy_wait: float = 10.0, settle_time: float = 0.5):
    """Waits until the SAP session reports not-busy and data has rendered."""
    end_time = time.time() + max_busy_wait
    while time.time() < end_time:
        try:
            is_busy = False
            if hasattr(session, "Busy") and session.Busy:
                is_busy = True
            elif hasattr(session, "Children") and session.Children.Count > 0:
                wnd = session.findById("wnd[0]", False)
                if wnd and getattr(wnd, "Busy", False):
                    is_busy = True

            if not is_busy:
                break
        except Exception:
            break
        time.sleep(0.3)

    time.sleep(settle_time)


def goto_tcode(session, tcode: str, wait_seconds: float = 1.0) -> bool:
    """
    Navigates to a T-code cleanly from any active screen.
    Method 1: Native StartTransaction() API (Recommended by SAP).
    Method 2: okcd toolbar entry fallback.
    """
    clean_tcode = tcode.strip().upper().replace("/N", "")
    dismiss_popups(session)

    # 1. Primary: Native StartTransaction
    try:
        session.StartTransaction(clean_tcode)
        time.sleep(wait_seconds)
        wait_until_not_busy(session)
        dismiss_popups(session)
        return True
    except Exception as ex_start:
        log.debug(f"StartTransaction({clean_tcode}) note: {ex_start}, trying okcd fallback...")

    # 2. Fallback: okcd command box
    try:
        dismiss_popups(session)
        ok_code = session.findById("wnd[0]/tbar[0]/okcd", False)
        if ok_code:
            ok_code.text = f"/n{clean_tcode}"
            session.findById("wnd[0]").sendVKey(0)
            time.sleep(wait_seconds)
            wait_until_not_busy(session)
            dismiss_popups(session)
            return True
    except Exception as ex_okcd:
        log.warning(f"Failed to navigate to {clean_tcode}: {ex_okcd}")

    return False


def open_tcode(session, tcode: str, wait_seconds: float = 1.5, max_busy_wait: float = 10.0) -> bool:
    """Opens a transaction and verifies navigation."""
    log.info(f"Opening T-code via scripting: {tcode}")
    success = goto_tcode(session, tcode, wait_seconds=wait_seconds)
    if not success:
        return False

    wait_until_not_busy(session, max_busy_wait=max_busy_wait)
    try:
        current_tcode = getattr(session.Info, "Transaction", "")
        log.info(f"After opening {tcode}, session.Info.Transaction = '{current_tcode}'")
        return tcode.upper().replace("/N", "") in current_tcode.upper()
    except Exception:
        return True