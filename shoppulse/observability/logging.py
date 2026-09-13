"""Structured JSON logging with conservative secret redaction."""

import logging
import re

import structlog

_SENSITIVE = re.compile(r"(?i)(password|api[_-]?key|authorization|postgres(?:ql)?://|redis://|email|phone)")


def _redact(_, __, event_dict):
    for key, value in list(event_dict.items()):
        if _SENSITIVE.search(str(key)) or _SENSITIVE.search(str(value)):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO", service: str = "shoppulse") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.stdlib.add_log_level,
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
    )
    structlog.contextvars.bind_contextvars(service=service)


def get_logger():
    return structlog.get_logger()
