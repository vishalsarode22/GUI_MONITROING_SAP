"""
Per-T-code action sequences, translated from SAP GUI Script Recorder recordings.
"""

import time
import re
from datetime import datetime, timedelta

from sap_gui.field_extractor import get_grid_row_count, get_status_text
from sap_gui.tcode_navigator import goto_tcode, wait_until_not_busy
from utils.logger import get_logger

log = get_logger(__name__, "tcode_actions")


def _optional(session, wnd_id: str, fn, description: str = ""):
    try:
        obj = session.findById(wnd_id, False)
        if obj is not None:
            fn(obj)
    except Exception as e:
        log.debug(f"Optional step skipped ({description or wnd_id}): {e}")


def action_al08(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "AL08")
    path = capture()

    session_summary = None
    if path:
        text = run_ocr(path)
        match = re.search(r"(\d+)\s*user logons with\s*(\d+)\s*back-end sessions", text, re.IGNORECASE)
        if match:
            session_summary = f"{match.group(1)} user logons with {match.group(2)} back-end sessions"

    return {"session_summary": session_summary} if session_summary else {}


def action_db01(session, capture):
    goto_tcode(session, "DB01")
    _optional(session, "wnd[0]/shellcont[1]/shell/shellcont[1]/shell",
              lambda o: setattr(o, "hierarchyHeaderWidth", 258), "DB01 header width")
    capture()
    return {}


def action_db02(session, capture):
    goto_tcode(session, "DB02")
    _optional(session, "wnd[0]/shellcont[1]/shell/shellcont[1]/shell",
              lambda o: setattr(o, "hierarchyHeaderWidth", 258), "DB02 header width")
    try:
        tree = session.findById("wnd[0]/shellcont[1]/shell/shellcont[1]/shell", False)
        if tree is not None:
            tree.expandNode("        100")
            tree.topNode = "        100"
            tree.selectItem("        101", "Task")
            tree.ensureVisibleHorizontalItem("        101", "Task")
            tree.doubleClickItem("        101", "Task")
            wait_until_not_busy(session)
    except Exception as e:
        log.debug(f"DB02 tree navigation note: {e}")
    capture()
    return {}


def action_db12(session, capture):
    goto_tcode(session, "DB12")
    _optional(session, "wnd[0]/usr/cntlBACKUPCAT_ALV_CONTAINER/shellcont/shell",
              lambda o: setattr(o, "currentCellColumn", "SYS_END_TIME"), "DB12 sort column")
    capture()
    return {}


def action_scot(session, capture):
    goto_tcode(session, "SCOT")
    try:
        tree = session.findById(
            "wnd[0]/usr/subCONTENT:SAPLSBCS_ADM:0104/subSUB_CONTENT:SAPLSBCS_NODES:0100/"
            "cntlSMTP_NODES_COLUMN_TREE_CONT/shellcont/shell",
            False
        )
        if tree is not None:
            tree.selectItem("SMTP", "Mail_Port")
            tree.ensureVisibleHorizontalItem("SMTP", "Mail_Port")
    except Exception as e:
        log.debug(f"SCOT SMTP node note: {e}")
    capture()
    return {}


def action_sm12(session, capture):
    goto_tcode(session, "SM12")
    try:
        user_field = session.findById("wnd[0]/usr/txtSEQG3-GUNAME", False)
        if user_field:
            user_field.text = ""  # blank = all users
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)  # F8 Execute
        wait_until_not_busy(session)
    except Exception as e:
        log.debug(f"SM12 execute note: {e}")

    capture()
    row_count = get_grid_row_count(
        session, "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell"
    )
    return {"lock_count": row_count} if row_count is not None else {}


def action_sm13(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SM13")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    update_summary = None
    if path:
        text = run_ocr(path)
        match = re.search(r"(\d+)\s*Update records?\s*found", text, re.IGNORECASE)
        if match:
            update_summary = f"{match.group(1)} Update records found"

    return {"update_summary": update_summary} if update_summary else {}


def action_sm21(session, capture):
    goto_tcode(session, "SM21")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    _optional(session, "wnd[0]/usr/cntlCONTAINER_0100/shellcont/shell/shellcont[1]/shell",
              lambda o: o.selectColumn("TEXT"), "SM21 select TEXT column")
    capture()
    return {}


def action_sm37_active(session, capture):
    from sap_gui.ocr_extractor import run_ocr, count_time_prefixed_rows

    goto_tcode(session, "SM37")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    try:
        _optional(session, "wnd[0]/usr/ctxtBTCH2170-FROM_DATE", lambda o: setattr(o, "text", yesterday))
        _optional(session, "wnd[0]/usr/chkBTCH2170-SCHEDUL", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/chkBTCH2170-FINISHED", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/chkBTCH2170-ABORTED", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/txtBTCH2170-USERNAME", lambda o: setattr(o, "text", "*"))
        
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    still_on_selection = True
    try:
        session.findById("wnd[0]/usr/chkBTCH2170-SCHEDUL", False)
    except Exception:
        still_on_selection = False

    if still_on_selection:
        return {"active_jobs": 0}

    job_count = count_time_prefixed_rows(run_ocr(path)) if path else None
    return {"active_jobs": job_count} if job_count is not None else {"active_jobs": 0}


def action_sm37_cancelled(session, capture):
    from sap_gui.ocr_extractor import run_ocr, count_time_prefixed_rows

    goto_tcode(session, "SM37")
    today = datetime.now().strftime("%d.%m.%Y")
    try:
        _optional(session, "wnd[0]/usr/ctxtBTCH2170-FROM_DATE", lambda o: setattr(o, "text", today))
        _optional(session, "wnd[0]/usr/chkBTCH2170-SCHEDUL", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/chkBTCH2170-READY", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/chkBTCH2170-RUNNING", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/chkBTCH2170-FINISHED", lambda o: setattr(o, "selected", False))
        _optional(session, "wnd[0]/usr/txtBTCH2170-USERNAME", lambda o: setattr(o, "text", "*"))

        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    still_on_selection = True
    try:
        session.findById("wnd[0]/usr/chkBTCH2170-SCHEDUL", False)
    except Exception:
        still_on_selection = False

    if still_on_selection:
        return {"cancelled_jobs": 0}

    job_count = count_time_prefixed_rows(run_ocr(path)) if path else None
    return {"cancelled_jobs": job_count} if job_count is not None else {"cancelled_jobs": 0}


def action_sm51(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SM51")
    grid_id = "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell/shellcont[1]/shell"
    _optional(session, grid_id, lambda o: o.selectAll(), "SM51 select all servers")
    path = capture()

    if not path:
        return {}

    text = run_ocr(path)
    match = re.search(r"(\d+)\s*AS instance\(s\)\s*started", text, re.IGNORECASE)
    if match:
        return {"instances_started": int(match.group(1))}
    return {"instances_started": 1}


def action_sm58(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SM58")
    try:
        _optional(session, "wnd[0]/usr/txtBENUTZER-LOW", lambda o: setattr(o, "text", "*"))
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    if not path:
        return {}

    text = run_ocr(path)
    if "Nothing was selected" in text or "Nothing selected" in text:
        return {"trfc_status": "Nothing was selected"}
    return {"trfc_status": "No backlog"}


def action_sm66(session, capture):
    from sap_gui.ocr_extractor import run_ocr, count_occurrences

    goto_tcode(session, "SM66")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[13]", False)
        if btn:
            btn.press()
            wait_until_not_busy(session)
    except Exception:
        pass

    _optional(
        session,
        "wnd[0]/usr/cntlGRID1/shellcont/shell/shellcont[1]/shell/shellcont[1]/shell",
        lambda o: setattr(o, "currentCellColumn", "STATE_INFO_DISP"),
        "SM66 sort column",
    )
    path = capture()
    if not path:
        return {}

    text = run_ocr(path)
    process_rows = len(re.findall(r"\d:\d{2}:\d{2}", text))
    running_count = count_occurrences(text, "Running")

    result = {}
    if process_rows:
        result["visible_process_rows"] = process_rows
    result["running_processes"] = running_count
    return result


def action_smlg(session, capture):
    goto_tcode(session, "SMLG")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[5]", False)
        if btn:
            btn.press()
            wait_until_not_busy(session)
    except Exception:
        pass
    capture()
    return {}


def action_smq1(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SMQ1")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    result = {"entries_displayed": 0, "queues_displayed": 0}
    if path:
        text = run_ocr(path)
        if "Nothing selected" not in text:
            entries = re.search(r"Number of Entries Displayed:\s*(\d+)", text)
            queues = re.search(r"Number of Queues Displayed:\s*(\d+)", text)
            if entries:
                result["entries_displayed"] = int(entries.group(1))
            if queues:
                result["queues_displayed"] = int(queues.group(1))
    return result


def action_smq2(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SMQ2")
    try:
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    path = capture()
    result = {"entries_displayed": 0, "queues_displayed": 0}
    if path:
        text = run_ocr(path)
        if "Nothing selected" not in text:
            entries = re.search(r"Number of Entries Displayed:\s*(\d+)", text)
            queues = re.search(r"Number of Queues Displayed:\s*(\d+)", text)
            if entries:
                result["entries_displayed"] = int(entries.group(1))
            if queues:
                result["queues_displayed"] = int(queues.group(1))
    return result


def action_sost(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "SOST")
    try:
        base = ("wnd[0]/usr/subSUB:SAPLSBCS_OUT:1100/subTOPSUB:SAPLSBCS_OUT:1110/"
                "tabsTAB1/tabpTAB1_FC1/ssubTAB1_SCA:SAPLSBCS_OUT:0003")
        max_sel = session.findById(f"{base}/txtG_MAXSEL", False)
        if max_sel:
            max_sel.text = "50000"
        refr_btn = session.findById(f"{base}/btnREFRICO2", False)
        if refr_btn:
            refr_btn.press()
        wait_until_not_busy(session)
    except Exception as e:
        log.debug(f"SOST refresh step note: {e}")
    path = capture()

    if not path:
        return {}

    text = run_ocr(path)
    match = re.search(
        r"(\d+)\s*Send Requests\s*(\d+)\s*Waiting\s*(\d+)\s*Sent\s*(\d+)\s*Errors",
        text, re.IGNORECASE
    )
    if match:
        return {
            "send_requests": int(match.group(1)),
            "waiting": int(match.group(2)),
            "sent": int(match.group(3)),
            "errors": int(match.group(4)),
        }
    return {}


def action_sp01(session, capture):
    from sap_gui.ocr_extractor import run_ocr, count_spool_rows

    goto_tcode(session, "SP01")
    try:
        base = "wnd[0]/usr/tabsTABSTRIP_BL1/tabpSCR1/ssub%_SUBSCREEN_BL1:RSPOSP01NR:0100"
        _optional(session, f"{base}/txtS_RQOWNE-LOW", lambda o: setattr(o, "text", "*"))
        btn = session.findById("wnd[0]/tbar[1]/btn[8]", False)
        if btn:
            btn.press()
        else:
            session.findById("wnd[0]").sendVKey(8)
        wait_until_not_busy(session)
    except Exception:
        pass

    _optional(session, "wnd[1]/usr/btnSEL2", lambda o: o.press(), "SP01 popup select-all")
    _optional(session, "wnd[0]/tbar[0]/btn[83]", lambda o: o.press(), "SP01 toolbar action")
    wait_until_not_busy(session)
    path = capture()

    spool_count = count_spool_rows(run_ocr(path)) if path else None
    return {"spool_count_visible": spool_count} if spool_count is not None else {"spool_count_visible": 0}


def action_st03n(session, capture):
    from sap_gui.ocr_extractor import run_ocr

    goto_tcode(session, "ST03N")
    try:
        tree = session.findById("wnd[0]/shellcont/shell/shellcont[1]/shell", False) or session.findById("wnd[0]/usr/cntlNAV_CONTAINER/shellcont/shell", False)
        if tree is not None:
            for node_key in ["B.999", "TOTAL;Day;Current", "TOTAL", "Day"]:
                try:
                    tree.selectedNode = node_key
                    tree.doubleClickNode(node_key)
                    wait_until_not_busy(session)
                    break
                except Exception:
                    continue
    except Exception as e:
        log.debug(f"ST03N tree navigation note: {e}")

    _optional(session, "wnd[1]/usr/btnBUTTON_2", lambda o: o.press(), "ST03N confirm popup")
    wait_until_not_busy(session)
    path = capture()

    if not path:
        return {}

    text = run_ocr(path)
    match = re.search(r"DIALOG\s+(\d+)\s+([\d.,]+)", text)
    if match:
        return {"dialog_avg_response_time_ms": match.group(2)}
    return {}


def action_st22_yesterday(session, capture):
    from sap_gui.ocr_extractor import run_ocr, count_date_prefixed_lines

    goto_tcode(session, "ST22")

    pressed_yesterday = False
    for btn_id in ["wnd[0]/usr/btnYESTERD", "wnd[0]/usr/btnBUTTON_YESTERDAY", "wnd[0]/usr/btn%_AUTOTEXT001"]:
        try:
            btn = session.findById(btn_id, False)
            if btn and getattr(btn, "Changeable", True):
                btn.press()
                wait_until_not_busy(session)
                pressed_yesterday = True
                break
        except Exception:
            continue

    if not pressed_yesterday:
        try:
            session.findById("wnd[0]").sendVKey(8)  # F8
            wait_until_not_busy(session)
        except Exception:
            pass

    # Dismiss modal popup if 0 dumps
    try:
        if session.Children.Count > 1:
            active_wnd = session.ActiveWindow
            if active_wnd and getattr(active_wnd, "Type", "") == "GuiModalWindow":
                active_wnd.sendVKey(0)
                wait_until_not_busy(session)
                capture("yesterday")
                return {"dump_count": 0}
    except Exception:
        pass

    yesterday_path = capture("yesterday")
    dump_count = 0
    if yesterday_path:
        text = run_ocr(yesterday_path)
        if "No runtime errors found" in text or "no dump" in text.lower():
            dump_count = 0
        else:
            counted = count_date_prefixed_lines(text)
            dump_count = counted if counted is not None else 0

    return {"dump_count": dump_count}


ACTIONS = {
    "al08": action_al08,
    "db01": action_db01,
    "db02": action_db02,
    "db12": action_db12,
    "scot": action_scot,
    "sm12": action_sm12,
    "sm13": action_sm13,
    "sm21": action_sm21,
    "sm37_active": action_sm37_active,
    "sm37_cancelled": action_sm37_cancelled,
    "sm51": action_sm51,
    "sm58": action_sm58,
    "sm66": action_sm66,
    "smlg": action_smlg,
    "smq1": action_smq1,
    "smq2": action_smq2,
    "sost": action_sost,
    "sp01": action_sp01,
    "st03n": action_st03n,
    "st22_yesterday": action_st22_yesterday,
}