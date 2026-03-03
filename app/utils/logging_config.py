"""
utils/logging_config.py — Centralised logging setup
=====================================================
Configures Python's logging module for the entire application.

WHY centralised logging?
- Consistent format across all modules.
- Single place to change log level.
- We can add file-based logging for production later.

SECURITY NOTES:
- Passwords must NEVER appear in log messages.
- We log authentication attempts (success/failure) for audit
  trails — a common compliance requirement.
"""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger with a sensible format.

    Format includes:
    - Timestamp (for correlating events)
    - Log level
    - Module name (so we know which file produced the message)
    - The message itself
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Stream handler → stdout (Gunicorn captures stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(numeric_level)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Avoid duplicate handlers if called more than once
    if not root.handlers:
        root.addHandler(handler)
