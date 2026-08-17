"""
Sends the final monitoring report email with PDF and Excel attached.
Supports custom Sender (From), Sender Password, Multiple To, and Multiple CC.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os
import yaml
import time

from core.models import MonitoringResult
from utils.logger import get_logger

log = get_logger(__name__, "email")

STATUS_COLORS = {
    "NORMAL": "#2e7d32",
    "HEALTHY": "#2e7d32",
    "WARNING": "#e65100",
    "CRITICAL": "#c62828",
    "UNKNOWN": "#616161"
}

EMAIL_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "email_config.yaml"
)


def _load_ui_email_settings() -> dict:
    if os.path.exists(EMAIL_CONFIG_PATH):
        try:
            with open(EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            log.debug(f"Could not read {EMAIL_CONFIG_PATH}: {e}")
    return {}


def _parse_email_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, list):
        return [str(e).strip() for e in val if str(e).strip()]
    if isinstance(val, str):
        return [e.strip() for e in val.replace(";", ",").split(",") if e.strip()]
    return []


def _build_report_html(result: MonitoringResult) -> str:
    status_val = getattr(result.overall_status, "value", str(getattr(result, "overall_status", "NORMAL")))
    status_color = STATUS_COLORS.get(status_val, "#616161")
    
    critical_count = len(result.critical_metrics()) if hasattr(result, "critical_metrics") else 0
    warning_count = len([m for m in result.metrics if getattr(m.status, "value", str(m.status)) == "WARNING"]) if hasattr(result, "metrics") else 0

    ai = getattr(result, "ai_analysis", None)
    ai_block = ""
    if ai:
        severity = getattr(ai, "severity", "NORMAL")
        likely_cause = getattr(ai, "likely_root_cause", getattr(ai, "root_cause", "Optimal operating baseline."))
        confidence = getattr(ai, "confidence", "HIGH")
        ai_block = f"""
        <div style="background:#f8f9fb;border-radius:6px;padding:16px 20px;margin-top:20px;border-left:4px solid {status_color};">
          <div style="font-size:12px;font-weight:700;color:#888;margin-bottom:6px;letter-spacing:0.5px;">AI ANALYSIS</div>
          <div style="font-size:14px;color:#222;margin-bottom:4px;"><b>Severity:</b> {severity}</div>
          <div style="font-size:14px;color:#222;margin-bottom:4px;"><b>Root Cause:</b> {likely_cause}</div>
          <div style="font-size:14px;color:#222;"><b>Confidence:</b> {confidence}</div>
        </div>"""

    metrics_count = len(getattr(result, "metrics", []))

    return f"""\
<html>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f7;padding:24px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
        <tr>
          <td style="background:#1e293b;padding:24px 28px;">
            <span style="color:#ffffff;font-size:20px;font-weight:700;">SAP BASIS Monitoring Report</span><br>
            <span style="color:#94a3b8;font-size:13px;">System: {getattr(result, 'system', 'SAP')} / Client: {getattr(result, 'client', '000')}</span>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 28px;">
            <div style="display:inline-block;background:{status_color}1a;color:{status_color};font-weight:700;font-size:15px;padding:8px 16px;border-radius:20px;margin-bottom:16px;">
              {status_val}
            </div>
            <table cellpadding="0" cellspacing="0" style="width:100%;margin:12px 0 4px 0;">
              <tr>
                <td style="color:#888;font-size:13px;padding:4px 0;">Cycle time</td>
                <td style="color:#222;font-size:13px;font-weight:600;padding:4px 0;">{getattr(result, 'cycle_timestamp', time.strftime('%Y-%m-%d %H:%M:%S'))}</td>
              </tr>
              <tr>
                <td style="color:#888;font-size:13px;padding:4px 0;">Metrics evaluated</td>
                <td style="color:#222;font-size:13px;font-weight:600;padding:4px 0;">{metrics_count}</td>
              </tr>
              <tr>
                <td style="color:#888;font-size:13px;padding:4px 0;">Critical / Warning</td>
                <td style="color:#222;font-size:13px;font-weight:600;padding:4px 0;">{critical_count} / {warning_count}</td>
              </tr>
            </table>
            {ai_block}
            <div style="margin-top:20px;font-size:13px;color:#666;line-height:1.5;">
              Full metric breakdown, AI recommendations, and T-code evidence screenshots are
              attached as a PDF report. Historical monitoring data is attached as an Excel file.
            </div>
          </td>
        </tr>
        <tr>
          <td style="background:#fafafa;padding:16px 28px;text-align:center;">
            <span style="color:#aaa;font-size:11px;">SAP BASIS AI Monitoring Agent -- Automated Report</span>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>
"""


def send_final_report(result: MonitoringResult, smtp_config: dict = None,
                      pdf_path: str = None, excel_path: str = None, max_retries: int = 2) -> bool:
    smtp_config = smtp_config or {}
    ui_cfg = _load_ui_email_settings()

    from_addr = ui_cfg.get("sender_email") or smtp_config.get("from_email") or smtp_config.get("sender_email") or smtp_config.get("username", "")
    password = ui_cfg.get("sender_password") or smtp_config.get("password", "")
    to_list = _parse_email_list(ui_cfg.get("recipients") or smtp_config.get("to_emails") or smtp_config.get("recipients"))
    cc_list = _parse_email_list(ui_cfg.get("cc_recipients") or smtp_config.get("cc_emails") or smtp_config.get("cc_recipients"))

    if not from_addr:
        log.warning("Sender email is missing. Skipping report email delivery.")
        return False

    if not to_list and not cc_list:
        log.warning("No To/CC recipients configured. Skipping report email delivery.")
        return False

    sys_name = getattr(result, "system", "SAP")
    status_val = getattr(result.overall_status, "value", str(getattr(result, "overall_status", "NORMAL")))
    subject = f"[{status_val}] SAP BASIS Monitoring Report - {sys_name}"

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(_build_report_html(result), "html"))
    msg.attach(alt)

    # Attach PDF and Excel
    for file_path in [pdf_path, excel_path]:
        if not file_path or not os.path.exists(file_path):
            continue
        try:
            with open(file_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
            part["Content-Disposition"] = f'attachment; filename="{os.path.basename(file_path)}"'
            msg.attach(part)
        except Exception as e:
            log.error(f"Failed to attach {file_path}: {e}")

    all_recipients = list(dict.fromkeys(to_list + cc_list))

    host = ui_cfg.get("smtp_host") or smtp_config.get("host") or smtp_config.get("smtp_host", "smtp.gmail.com")
    port = int(ui_cfg.get("smtp_port") or smtp_config.get("port") or smtp_config.get("smtp_port", 587))
    username = from_addr

    for attempt in range(1, max_retries + 1):
        try:
            with smtplib.SMTP(host, port, timeout=60) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if password:
                    server.login(username, password)
                server.sendmail(from_addr, all_recipients, msg.as_string())
            
            log.info(f"Final report email sent successfully to To: {to_list} | CC: {cc_list}")
            return True
        except Exception as e:
            log.warning(f"Email delivery attempt {attempt}/{max_retries} failed: {e}")
            if attempt == max_retries:
                log.error(f"Email failed after {max_retries} attempts: {e}")
                return False
            time.sleep(3)

    return False