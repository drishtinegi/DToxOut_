"""
Centralized logging configuration.

Provides :func:`configure_logging` to set up application-wide logging
with a consistent format and sensitive-data filtering.

Supported formats (set via ``LOG_FORMAT``):
- ``text``  — human-readable ``%(asctime)s [%(levelname)s] %(name)s: %(message)s``
- ``keyvalue`` — ``level=INFO module=app.api.scan msg="..."``
- ``json``  — one JSON object per line

A :class:`SensitiveFilter` scrubs passwords, tokens, secrets, and
database URLs from log output before they reach any handler.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Sensitive-data filter
# ---------------------------------------------------------------------------

# Patterns that indicate sensitive values.  The filter replaces any
# match with ``[FILTERED]`` in the log output.
_SENSITIVE_PATTERNS: list[re.Pattern[str]] = [
    # Database connection strings (contain embedded passwords)
    re.compile(
        r"(postgresql|mysql|mongodb|redis)://[^\s]+",
        re.IGNORECASE,
    ),
    # Bearer tokens in Authorization headers
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    # Generic "key", "secret", "token", "password" assignments
    re.compile(
        r"""((?:password|passwd|secret|token|api_key|apikey|auth)["']?\s*[:=]\s*)["']?[^\s,"'}]+["']?""",
        re.IGNORECASE,
    ),
    # Long hex strings that look like secrets (32+ hex chars)
    re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE),
]


class SensitiveFilter(logging.Filter):
    """Log filter that scrubs sensitive values from log records.

    Applied to the root logger so every log line passes through it
    before reaching any handler (file, stdout, etc.).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Replace sensitive patterns in the log message.

        Modifies ``record.msg`` in place so that downstream formatters
        and handlers never see the raw secret values.
        """
        if isinstance(record.msg, str):
            for pattern in _SENSITIVE_PATTERNS:
                record.msg = pattern.sub("[FILTERED]", record.msg)
        return True


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class _KeyValueFormatter(logging.Formatter):
    """``level=INFO module=app.api.scan msg="Analysis completed"``"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        parts = [
            f"ts={ts}",
            f"level={record.levelname}",
            f"module={record.name}",
        ]
        if hasattr(record, "request_id"):
            parts.append(f"request_id={record.request_id}")
        msg = record.getMessage()
        if record.exc_info and record.exc_info[1] is not None:
            msg = f"{msg} exc={self.formatException(record.exc_info)}"
        return f"{' '.join(parts)} msg=\"{msg}\""


class _TextFormatter(logging.Formatter):
    """Standard ``2025-01-15 10:30:00 [INFO] app.api.scan: Analysis completed``"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


class _JSONFormatter(logging.Formatter):
    """One JSON object per line for machine-parseable logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


_FORMATTERS: dict[str, logging.Formatter] = {
    "text": _TextFormatter(),
    "keyvalue": _KeyValueFormatter(),
    "json": _JSONFormatter(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def configure_logging(
    level: str = "INFO",
    fmt: str = "keyvalue",
) -> None:
    """Configure application-wide logging.

    Sets the root logger level and attaches a
    :class:`SensitiveFilter` plus a formatter chosen by *fmt*.

    This function is idempotent — calling it more than once replaces
    the previous configuration.

    Args:
        level: Standard Python log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        fmt: One of ``"text"``, ``"keyvalue"``, or ``"json"``.
    """
    root = logging.getLogger()

    # Remove any pre-existing handlers to avoid duplicate output.
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    # Clear accumulated logger-level filters (from prior configure_logging calls).
    root.filters.clear()

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    # Formatter from the registry (falls back to keyvalue).
    formatter = _FORMATTERS.get(fmt, _FORMATTERS["keyvalue"])

    # Sensitive-data filter is attached to the handler (not the root logger)
    # because Python's callHandlers() walks the parent chain to find handlers
    # but does NOT run parent loggers' filters during propagation.
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(SensitiveFilter())
    handler.setFormatter(formatter)
    root.addHandler(handler)
