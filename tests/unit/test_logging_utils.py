"""Unit tests for src/common/logging_utils.py."""

from __future__ import annotations

import json
import logging

from src.common.logging_utils import JsonFormatter, get_logger


def test_json_formatter_produces_valid_json_with_expected_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="something_happened",
        args=None,
        exc_info=None,
    )
    record.custom_field = "custom_value"

    formatted = formatter.format(record)
    payload = json.loads(formatted)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert payload["message"] == "something_happened"
    assert payload["line"] == 42
    assert payload["custom_field"] == "custom_value"


def test_get_logger_is_idempotent_and_writes_json(capsys) -> None:
    logger = get_logger("hcai.test.logger")
    handler_count_first = len(logger.handlers)

    # Calling again should not add a duplicate handler.
    logger_again = get_logger("hcai.test.logger")
    assert logger is logger_again
    assert len(logger_again.handlers) == handler_count_first

    logger.info("hello_world", extra={"foo": "bar"})

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["message"] == "hello_world"
    assert payload["foo"] == "bar"
