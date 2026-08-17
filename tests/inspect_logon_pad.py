import sys
from pywinauto import Desktop

def inspect_sap_logon():
    desktop = Desktop(backend="uia")
    sap_window = None
    
    for win in desktop.windows():
        title = win.window_text().lower()
        if "sap logon" in title or "saplogon" in title:
            sap_window = win
            break
            
    if not sap_window:
        print("❌ Could not find an open SAP Logon window.")
        print("Please manually launch SAP Logon so the window is visible, then re-run.")
        sys.exit(1)
        
    print(f"✅ Found SAP Window: '{sap_window.window_text()}'\n")
    print("=" * 60)
    print("Detected Connection Items (Copy one of these into SAP_CONNECTION_NAME):")
    print("=" * 60)
    
    seen = set()
    for item in sap_window.descendants():
        txt = item.window_text().strip()
        control_type = getattr(item.element_info, "control_type", "")
        if txt and len(txt) > 1 and control_type in ["DataItem", "TreeItem", "ListItem", "Text"]:
            # Ignore standard menu labels and duplicates
            if txt not in seen and txt not in ["SAP Logon", "Connections", "Favorites", "Shortcuts"]:
                seen.add(txt)
                print(f"  • {txt}   [Control: {control_type}]")

if __name__ == "__main__":
    inspect_sap_logon()