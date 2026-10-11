"""
Structured Logging Foundation tests (Milestone 12 Step 5, Part 1).

Verifies:
    A. Logging configuration uses the configured log level
    B. Log output follows the chosen format (text, keyvalue, json)
    C. Sensitive values are never logged

Run with:
    pytest app/tests/test_logging.py -v
"""

from __future__ import annotations

import io
import json
import logging
import re

import pytest

from app.core.logging import (
    SensitiveFilter,
    _FORMATTERS,
    configure_logging,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _caplog_configure(
    level: str = "INFO",
    fmt: str = "keyvalue",
) -> tuple[logging.Logger, io.StringIO]:
    """Configure logging at the given level/format, attach a StringIO
    handler, and return (logger, stream) so tests can inspect output."""
    stream = io.StringIO()
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    configure_logging(level=level, fmt=fmt)

    # Remove the stderr handler added by configure_logging — we only want
    # the StringIO handler for test assertions.
    for h in root.handlers[:]:
        root.removeHandler(h)

    # Attach a StringIO handler with the real formatter + SensitiveFilter.
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_FORMATTERS[fmt])
    handler.addFilter(SensitiveFilter())
    root.addHandler(handler)

    return logging.getLogger("test.module"), stream


# ===========================================================================
# SECTION A — Logging configuration uses the configured log level
# ===========================================================================


class TestLogLevelConfiguration:
    """Verify that configure_logging sets the correct root log level."""

    def test_default_level_is_info(self) -> None:
        configure_logging()
        assert logging.getLogger().level == logging.INFO

    def test_debug_level(self) -> None:
        configure_logging(level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_warning_level(self) -> None:
        configure_logging(level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_error_level(self) -> None:
        configure_logging(level="ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_critical_level(self) -> None:
        configure_logging(level="CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_case_insensitive_level(self) -> None:
        configure_logging(level="info")
        assert logging.getLogger().level == logging.INFO

    def test_invalid_level_falls_back_to_info(self) -> None:
        configure_logging(level="NOT_A_REAL_LEVEL")
        assert logging.getLogger().level == logging.INFO

    def test_settings_log_level_int_property(self) -> None:
        from app.core.config import Settings

        assert Settings(LOG_LEVEL="DEBUG").log_level_int == logging.DEBUG
        assert Settings(LOG_LEVEL="WARNING").log_level_int == logging.WARNING
        assert Settings(LOG_LEVEL="INVALID").log_level_int == logging.INFO

    def test_debug_messages_suppressed_at_info_level(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="text")
        logger.debug("should not appear")
        configure_logging()  # reset
        assert "should not appear" not in stream.getvalue()

    def test_debug_messages_visible_at_debug_level(self) -> None:
        logger, stream = _caplog_configure(level="DEBUG", fmt="text")
        logger.debug("debug visible")
        configure_logging()  # reset
        assert "debug visible" in stream.getvalue()

    def test_info_messages_visible_at_info_level(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="text")
        logger.info("info visible")
        configure_logging()  # reset
        assert "info visible" in stream.getvalue()

    def test_warning_messages_visible_at_info_level(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="text")
        logger.warning("warning visible")
        configure_logging()  # reset
        assert "warning visible" in stream.getvalue()


# ===========================================================================
# SECTION B — Log output follows the chosen format
# ===========================================================================


class TestLogFormat:
    """Verify that output matches the configured format style."""

    def test_text_format_contains_level_and_module(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="text")
        logger.info("hello text")
        configure_logging()  # reset
        output = stream.getvalue()
        assert "[INFO" in output
        assert "test.module" in output
        assert "hello text" in output

    def test_keyvalue_format_contains_level_eq(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="keyvalue")
        logger.info("hello kv")
        configure_logging()  # reset
        output = stream.getvalue()
        assert "level=INFO" in output
        assert "msg=" in output
        assert "hello kv" in output

    def test_json_format_is_valid_json(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="json")
        logger.info("hello json")
        configure_logging()  # reset
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["msg"] == "hello json"
        assert "ts" in parsed
        assert "module" in parsed

    def test_json_format_includes_timestamp(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="json")
        logger.info("timestamp test")
        configure_logging()  # reset
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert "T" in parsed["ts"]  # ISO 8601 contains 'T'

    def test_keyvalue_format_includes_timestamp(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="keyvalue")
        logger.info("ts test")
        configure_logging()  # reset
        output = stream.getvalue()
        assert "ts=" in output

    def test_json_includes_exception_on_error(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="json")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.error("failed", exc_info=True)
        configure_logging()  # reset
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert "exc" in parsed
        assert "ValueError" in parsed["exc"]

    def test_keyvalue_includes_exception_on_error(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="keyvalue")
        try:
            raise RuntimeError("oops")
        except RuntimeError:
            logger.error("broke", exc_info=True)
        configure_logging()  # reset
        output = stream.getvalue()
        assert "exc=" in output
        assert "RuntimeError" in output

    def test_text_includes_exception_on_error(self) -> None:
        logger, stream = _caplog_configure(level="INFO", fmt="text")
        try:
            raise KeyError("missing")
        except KeyError:
            logger.error("key err", exc_info=True)
        configure_logging()  # reset
        output = stream.getvalue()
        assert "KeyError" in output


# ===========================================================================
# SECTION C — Sensitive values are never logged
# ===========================================================================


class TestSensitiveFilter:
    """Verify the SensitiveFilter scrubs secrets from log output."""

    def test_database_url_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Connecting to postgresql://user:pass@host/db",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "pass@host" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_mysql_url_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="DSN=mysql://admin:s3cret@localhost/mydb",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "s3cret" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_bearer_token_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload.signature",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "eyJhbGci" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_password_in_string_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="password=mySecret123 login attempt failed",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "mySecret123" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_secret_key_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="secret: abcdef1234567890abcdef1234567890",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "abcdef1234567890" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_long_hex_string_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="token=a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_safe_message_not_filtered(self) -> None:
        """Normal log messages without sensitive data must pass through unchanged."""
        f = SensitiveFilter()
        original = "Analysis completed for user abc-123 with 5 ingredients"
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=original,
            args=(), exc_info=None,
        )
        f.filter(record)
        assert record.msg == original

    def test_user_id_not_filtered(self) -> None:
        """UUIDs that are user IDs should NOT be filtered (they're not secrets)."""
        f = SensitiveFilter()
        msg = "User 550e8400-e29b-41d4-a716-446655440000 logged in"
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=msg,
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "550e8400-e29b-41d4-a716-446655440000" in record.msg

    def test_filter_always_returns_true(self) -> None:
        """The filter should always return True (allow the record through)."""
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="anything",
            args=(), exc_info=None,
        )
        assert f.filter(record) is True

    def test_api_key_filtered(self) -> None:
        f = SensitiveFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="api_key=sk-proj-abc123def456ghi789",
            args=(), exc_info=None,
        )
        f.filter(record)
        assert "sk-proj-abc123" not in record.msg
        assert "[FILTERED]" in record.msg

    def test_no_passwords_in_output_end_to_end(self) -> None:
        """Integration: configure logging, emit a message with a password,
        verify the output stream has no password."""
        logger, stream = _caplog_configure(level="INFO", fmt="keyvalue")
        logger.info("password=hunter2 login attempt")
        configure_logging()  # reset
        output = stream.getvalue()
        assert "hunter2" not in output
        assert "[FILTERED]" in output

    def test_no_db_url_in_output_end_to_end(self) -> None:
        """Integration: verify DB URLs are filtered through the full pipeline."""
        logger, stream = _caplog_configure(level="INFO", fmt="json")
        logger.info("db=postgresql://admin:secret@db.host/prod")
        configure_logging()  # reset
        output = stream.getvalue().strip()
        parsed = json.loads(output)
        assert "secret@db.host" not in parsed["msg"]
        assert "[FILTERED]" in parsed["msg"]
