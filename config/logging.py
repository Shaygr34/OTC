"""Structured logging configuration — stdout + daily rotated file."""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FILE = _LOG_DIR / "engine.log"


def setup_logging(level: str = "INFO") -> None:
    """Configure structlog with JSON output to both stdout and file.

    File logs rotate daily, keeping 7 days of history.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Standard library logging setup (structlog renders, stdlib routes)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # Console handler (stdout)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    root_logger.addHandler(console)

    # File handler (daily rotation, keep 7 days)
    file_handler = TimedRotatingFileHandler(
        str(_LOG_FILE),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)

    # Structlog pipeline
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
