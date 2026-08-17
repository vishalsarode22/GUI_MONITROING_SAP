import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sap_gui.tcode_navigator import get_active_sap_session_window, open_tcode
from sap_gui.screenshot import capture_screenshot

if __name__ == "__main__":
    session = get_active_sap_session_window()
    open_tcode(session, "SM50", wait_seconds=4.0)
    path = capture_screenshot(session, "SM50")
    print(f"\nScreenshot saved at: {path}")