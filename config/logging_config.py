"""
StorageRationalizer — Centralized Logging Configuration

Referenced by: docs/MONITORING_AND_ALERTING.md
Usage: import this module at app startup to configure all loggers.

    from config.logging_config import setup_logging
    setup_logging()
"""

import logging
import logging.handlers
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"

# ---------------------------------------------------------------------------
# Log format
# ---------------------------------------------------------------------------

_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------


def setup_logging(level: int = logging.INFO) -> None:
    """
    Configure all application loggers.

    Creates logs/ directory if missing and attaches rotating file handlers
    for app, security, API, and file-operations log streams.

    Args:
        level: Root logging level (default: INFO).
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    # ── Root / app logger ──────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(level)

    if not root.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    app_handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
    )
    app_handler.setFormatter(formatter)
    root.addHandler(app_handler)

    # ── Security logger ────────────────────────────────────────────────────
    security_logger = logging.getLogger("security")
    security_handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "security.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,  # Longer retention for audit trail
    )
    security_handler.setLevel(logging.WARNING)
    security_handler.setFormatter(formatter)
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)

    # ── API logger ─────────────────────────────────────────────────────────
    api_logger = logging.getLogger("api")
    api_handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "api.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    api_handler.setFormatter(formatter)
    api_logger.addHandler(api_handler)
    api_logger.setLevel(logging.INFO)

    # ── File operations logger ─────────────────────────────────────────────
    file_logger = logging.getLogger("file_ops")
    file_handler = logging.handlers.RotatingFileHandler(
        _LOGS_DIR / "file_operations.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setFormatter(formatter)
    file_logger.addHandler(file_handler)
    file_logger.setLevel(logging.INFO)

    logging.getLogger(__name__).info("Logging configured. Log dir: %s", _LOGS_DIR)


# ---------------------------------------------------------------------------
# Convenience loggers (importable directly)
# ---------------------------------------------------------------------------

security_logger = logging.getLogger("security")
api_logger = logging.getLogger("api")
file_logger = logging.getLogger("file_ops")
