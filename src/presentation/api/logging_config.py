"""Structured (JSON) logging setup via structlog.

Called once at app startup (`app.py`'s lifespan). Every log call anywhere
in the app (`structlog.get_logger(__name__)`) picks up this configuration
automatically - there is no per-module setup needed beyond importing
structlog and calling `get_logger`.
"""

import logging

import structlog


def configure_logging(*, level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
