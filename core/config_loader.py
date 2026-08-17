"""
Loads configuration and secrets from .env.
Extend later to also load config/*.yaml files.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env in project root


def get_sap_credentials() -> dict:
    client = os.getenv("SAP_CLIENT")
    username = os.getenv("SAP_USERNAME")
    password = os.getenv("SAP_PASSWORD")
    language = os.getenv("SAP_LANGUAGE", "EN")

    missing = [name for name, val in
               [("SAP_CLIENT", client), ("SAP_USERNAME", username), ("SAP_PASSWORD", password)]
               if not val]
    if missing:
        raise ValueError(f"Missing required .env values: {', '.join(missing)}")

    return {
        "client": client,
        "username": username,
        "password": password,
        "language": language,
    }

def get_linux_ssh_credentials() -> dict:
    host = os.getenv("SSH_HOST")
    port = int(os.getenv("SSH_PORT", "22"))
    username = os.getenv("SSH_USERNAME")
    password = os.getenv("SSH_PASSWORD")

    missing = [name for name, val in
               [("SSH_HOST", host), ("SSH_USERNAME", username), ("SSH_PASSWORD", password)]
               if not val]
    if missing:
        raise ValueError(f"Missing required .env values: {', '.join(missing)}")

    return {"host": host, "port": port, "username": username, "password": password}


def get_sap_instance_nr() -> str:
    nr = os.getenv("SAP_INSTANCE_NR")
    if not nr:
        raise ValueError("Missing required .env value: SAP_INSTANCE_NR")
    return nr

import yaml

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")


def get_thresholds() -> dict:
    path = os.path.join(CONFIG_DIR, "thresholds.yaml")
    with open(path, "r") as f:
        return yaml.safe_load(f)

def get_smtp_config() -> dict:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("ALERT_FROM_EMAIL")
    to_emails_raw = os.getenv("ALERT_TO_EMAILS", "")
    to_emails = [e.strip() for e in to_emails_raw.split(",") if e.strip()]

    missing = [name for name, val in
               [("SMTP_HOST", host), ("SMTP_USERNAME", username),
                ("SMTP_PASSWORD", password), ("ALERT_FROM_EMAIL", from_email)]
               if not val]
    if missing:
        raise ValueError(f"Missing required .env values: {', '.join(missing)}")
    if not to_emails:
        raise ValueError("ALERT_TO_EMAILS must contain at least one recipient")

    return {
        "host": host, "port": port, "username": username, "password": password,
        "from_email": from_email, "to_emails": to_emails,
    }

def get_monitoring_tasks() -> list[dict]:
    path = os.path.join(CONFIG_DIR, "monitoring_tasks.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("tasks", [])

def get_launch_config() -> dict:
    exe_path = os.getenv("SAPLOGON_EXE_PATH")
    connection_name = os.getenv("SAP_CONNECTION_NAME")
    if not exe_path or not connection_name:
        raise ValueError("Missing SAPLOGON_EXE_PATH or SAP_CONNECTION_NAME in .env")
    return {"exe_path": exe_path, "connection_name": connection_name}

def get_ocr_patterns() -> dict:
    path = os.path.join(CONFIG_DIR, "ocr_patterns.yaml")
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def get_systems() -> list[dict]:
    path = os.path.join(CONFIG_DIR, "systems.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data.get("systems", [])


def add_system(name: str, client: str, connection_name: str,
                username: str, password: str, language: str = "EN"):
    path = os.path.join(CONFIG_DIR, "systems.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {"systems": []}
    data.setdefault("systems", []).append({
        "name": name, "client": client, "connection_name": connection_name,
        "username": username, "password": password, "language": language,
    })
    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def get_systems_safe() -> list[dict]:
    """Returns system list with passwords masked -- for API responses only."""
    systems = get_systems()
    return [
        {**s, "password": "••••••••"} for s in systems
    ]