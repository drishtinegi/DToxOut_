"""
Request/response logging middleware.

Records one structured log line per completed request containing:
- HTTP method
- Request path
- Response status code
- Request processing duration in milliseconds
- A unique request ID for distributed tracing

The request ID is also returned to the client in the ``X-Request-ID``
response header so that callers can correlate client-side errors with
server logs.

Sensitive data (passwords, tokens, Authorization headers, request /
response bodies) is **never** logged.  The centralized
:class:`~app.core.logging.SensitiveFilter` provides a safety net for
any accidental leakage.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger(__name__)

# Headers that may contain sensitive material — never logged.
_SENSITIVE_HEADERS: frozenset[str] = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "proxy-authorization",
})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Lightweight per-request logging middleware.

    On each request:
    1. A UUID4 ``request_id`` is generated and attached to
       ``request.state.request_id``.
    2. The request is timed.
    3. After the response is produced, a single INFO log line is emitted
       with ``method``, ``path``, ``status_code``, ``duration_ms``, and
       ``request_id``.
    4. The ``X-Request-ID`` header is added to the response.

    The log message embeds all fields as structured key=value pairs so
    that every configured formatter (text, keyvalue, json) renders them
    inside the ``msg`` field without requiring formatter changes.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "method=%s path=%s status=%d duration_ms=%.2f",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={
                    "request_id": request_id,
                },
            )

        response.headers["X-Request-ID"] = request_id
        return response
