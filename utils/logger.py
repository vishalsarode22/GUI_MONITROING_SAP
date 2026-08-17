import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_MAX_BYTES = 5 * 1024 * 1024  # 5MB per file
_BACKUP_COUNT = 5              # keep 5 rotated files (25MB total per log type)

_configured_loggers = {}


def get_logger(module_name: str, log_file: str = "application") -> logging.Logger:
    key = f"{module_name}:{log_file}"
    if key in _configured_loggers:
        return _configured_loggers[key]

    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if not logger.handlers:
        fh = RotatingFileHandler(
            os.path.join(LOG_DIR, f"{log_file}.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(_FORMAT))
        fh.setLevel(logging.DEBUG)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(_FORMAT))
        ch.setLevel(logging.INFO)

        eh = RotatingFileHandler(
            os.path.join(LOG_DIR, "errors.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
        eh.setFormatter(logging.Formatter(_FORMAT))
        eh.setLevel(logging.ERROR)

        logger.addHandler(fh)
        logger.addHandler(ch)
        logger.addHandler(eh)

    _configured_loggers[key] = logger
    return logger