"""
Rate limiting middleware and configuration.

Uses slowapi to provide per-IP rate limiting on FastAPI endpoints.
Limits are configurable through environment variables via Settings:

- RATE_LIMIT_DEFAULT  — default limit for un-decorated endpoints (60/minute)
- RATE_LIMIT_AUTH     — limit for authentication endpoints (5/minute)
- RATE_LIMIT_SCAN     — limit for scan analysis (10/minute)
- RATE_LIMIT_SEARCH   — limit for search endpoints (30/minute)

When a client exceeds their limit, a 429 Too Many Requests response
is returned with a safe, non-leaking message body.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """Extract client IP for rate-limit keying.

    ``X-Forwarded-For`` is client-controllable: the *left-most* entry can be
    forged by anyone. Each trusted proxy appends the address it saw to the
    *right*, so with ``TRUSTED_PROXY_COUNT`` proxies in front of the app the
    real client is the Nth entry from the right. With 0 trusted proxies the
    header is ignored and the socket peer address is used.
    """
    trusted = settings.TRUSTED_PROXY_COUNT
    xff = request.headers.get("X-Forwarded-For")
    if xff and trusted > 0:
        hops = [h.strip() for h in xff.split(",") if h.strip()]
        if hops:
            return hops[max(len(hops) - trusted, 0)]
    return get_remote_address(request)


# ---------------------------------------------------------------------------
# Limiter instance — import this in API modules to decorate routes
# ---------------------------------------------------------------------------

limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    headers_enabled=True,
)


# ---------------------------------------------------------------------------
# Exception handler — returns safe 429 JSON
# ---------------------------------------------------------------------------


async def _rate_limit_exceeded_handler(
    request: Request, exc: RateLimitExceeded
) -> JSONResponse:
    """Handle rate-limit breaches with a safe, non-leaking response.

    The response body contains only ``detail`` — no internal paths,
    IPs, or configuration values are exposed.
    """
    logger.warning(
        "Rate limit exceeded on %s %s detail=%s",
        request.method,
        request.url.path,
        exc.detail,
    )
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


# ---------------------------------------------------------------------------
# Setup helper — call once from main.py
# ---------------------------------------------------------------------------


def setup_rate_limiting(app: FastAPI) -> None:
    """Attach the rate limiter and its exception handler to *app*.

    Must be called after the app is created but before requests are served.
    """
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
