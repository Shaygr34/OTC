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

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Standard library logging setup (structlog renders, stdlib routes)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    # Shared formatter — structlog already renders JSON, so stdlib
    # handlers just pass through the pre-formatted string.
    formatter = logging.Formatter("%(message)s")

    # Console handler (stdout)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
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
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Structlog pipeline — renders JSON, then hands to stdlib for routing
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # Bridge to stdlib logging
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Configure ProcessorFormatter for all handlers so stdlib
    # logging also gets the JSON rendering
    json_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
    )
    for handler in root_logger.handlers:
        handler.setFormatter(json_formatter)
