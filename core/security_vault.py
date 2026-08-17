"""
Windows Credential Locker (Vault) Interface.
Stores and retrieves SAP and SMTP credentials securely from the Windows OS vault.
"""

import keyring
from utils.logger import get_logger

log = get_logger(__name__, "security_vault")
SERVICE_NAME = "SAP_BASIS_AI_MONITOR"


def save_credential(account_key: str, secret: str) -> bool:
    """Saves a secret into the Windows Credential Vault."""
    try:
        if secret is None:
            secret = ""
        keyring.set_password(SERVICE_NAME, account_key, secret)
        return True
    except Exception as e:
        log.error(f"Failed to store credential in Windows Vault for {account_key}: {e}")
        return False


def get_credential(account_key: str) -> str:
    """Retrieves a secret from the Windows Credential Vault."""
    try:
        pwd = keyring.get_password(SERVICE_NAME, account_key)
        return pwd or ""
    except Exception as e:
        log.error(f"Failed to retrieve credential from Windows Vault for {account_key}: {e}")
        return ""


def delete_credential(account_key: str) -> bool:
    """Deletes a credential from the Windows Vault."""
    try:
        keyring.delete_password(SERVICE_NAME, account_key)
        return True
    except Exception:
        return False