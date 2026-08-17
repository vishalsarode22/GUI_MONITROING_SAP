import win32com.client
import sys

try:
    sap_gui_auto = win32com.client.GetObject("SAPGUI")
    if not sap_gui_auto:
        print("❌ Could not get SAPGUI object from Windows ROT.")
        sys.exit(1)
        
    application = sap_gui_auto.GetScriptingEngine
    if not application:
        print("❌ Scripting Engine is not enabled on client.")
        sys.exit(1)

    print(f"✅ Scripting Engine active. Connections count: {application.Children.Count}")

    for i in range(application.Children.Count):
        conn = application.Children(i)
        print(f"  └── Connection [{i}]: Description='{conn.Description}', Sessions Count: {conn.Children.Count}")
        for j in range(conn.Children.Count):
            sess = conn.Children(j)
            print(f"       └── Session [{j}]: Info.Transaction='{sess.Info.Transaction}', Busy={sess.Busy}")

except Exception as e:
    print(f"Error inspecting SAP COM object: {e}")