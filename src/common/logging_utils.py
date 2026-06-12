"""Structured logging setup.

Provides a consistent, JSON-formatted logger across the data pipeline, ML
pipeline, scoring script, and Azure Function API so logs can be queried
uniformly in Application Insights / Log Analytics.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include any extra fields passed via `logger.info(..., extra={...})`
        reserved = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}
        for key, value in vars(record).items():
            if key not in reserved and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a module-level logger configured with JSON output to stdout.

    Idempotent: calling multiple times for the same ``name`` does not add
    duplicate handlers.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return logger
