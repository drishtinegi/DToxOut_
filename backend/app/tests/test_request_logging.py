"""
Request/Response Logging Middleware tests (Milestone 12 Step 5, Part 2).

Verifies:
    A. Requests produce a log entry
    B. Log contains the HTTP method
    C. Log contains the request path
    D. Log contains the response status code
    E. Log contains request duration/latency
    F. Log contains a request ID
    G. Different requests receive appropriate request IDs
    H. Sensitive headers/tokens are not written to logs
    I. X-Request-ID response header is present
    J. Existing behaviour unaffected (middleware does not break routes)

Run with:
    pytest app/tests/test_request_logging.py -v
"""

from __future__ import annotations

import io
import json
import logging
import re
import time
import uuid

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.logging import SensitiveFilter, _FORMATTERS, configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_logging_test_app() -> FastAPI:
    """Build a minimal FastAPI app with RequestLoggingMiddleware."""
    test_app = FastAPI(title="RequestLogging Test")
    test_app.add_middleware(RequestLoggingMiddleware)

    @test_app.get("/")
    async def root():
        return {"message": "ok"}

    @test_app.get("/slow")
    async def slow():
        time.sleep(0.05)
        return {"message": "slow"}

    @test_app.get("/error")
    async def error():
        raise ValueError("boom")

    @test_app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=500, content={"detail": "error"})

    @test_app.post("/items")
    async def create_item(request: Request):
        return {"created": True}

    @test_app.get("/health")
    async def health():
        return {"status": "healthy"}

    return test_app


def _setup_log_capture(
    fmt: str = "keyvalue",
) -> tuple[io.StringIO, logging.Handler]:
    """Attach a StringIO handler to root logger and return (stream, handler).

    Caller is responsible for calling ``configure_logging()`` to reset
    root state when done.
    """
    stream = io.StringIO()
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(stream)
    handler.setFormatter(_FORMATTERS[fmt])
    handler.addFilter(SensitiveFilter())
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return stream, handler


def _reset_logging() -> None:
    """Reset root logger to default state."""
    configure_logging(level="INFO", fmt="keyvalue")


def _make_client() -> TestClient:
    """Create a fresh TestClient with the RequestLoggingMiddleware."""
    return TestClient(_build_logging_test_app(), raise_server_exceptions=False)


# ===========================================================================
# SECTION A — Requests produce a log entry
# ===========================================================================


class TestRequestProducesLogEntry:
    """Every request must produce at least one log line."""

    def test_get_produces_log(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            output = stream.getvalue()
            assert "method=GET" in output
        finally:
            _reset_logging()

    def test_post_produces_log(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.post("/items")
            output = stream.getvalue()
            assert "method=POST" in output
        finally:
            _reset_logging()

    def test_404_produces_log(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/does-not-exist")
            output = stream.getvalue()
            assert "status=404" in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION B — Log contains the HTTP method
# ===========================================================================


class TestLogContainsMethod:
    """The logged method must match the actual request method."""

    def test_get_method(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            assert "method=GET" in stream.getvalue()
        finally:
            _reset_logging()

    def test_post_method(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.post("/items")
            assert "method=POST" in stream.getvalue()
        finally:
            _reset_logging()

    def test_put_method(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.put("/items")
            assert "method=PUT" in stream.getvalue()
        finally:
            _reset_logging()

    def test_delete_method(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.delete("/items")
            assert "method=DELETE" in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION C — Log contains the request path
# ===========================================================================


class TestLogContainsPath:
    """The logged path must match the actual request path."""

    def test_root_path(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            assert "path=/" in stream.getvalue()
        finally:
            _reset_logging()

    def test_named_path(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/health")
            assert "path=/health" in stream.getvalue()
        finally:
            _reset_logging()

    def test_unknown_path_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/unknown/abc")
            assert "path=/unknown/abc" in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION D — Log contains the response status code
# ===========================================================================


class TestLogContainsStatusCode:
    """The logged status code must match the actual response status."""

    def test_200(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/")
            assert f"status={resp.status_code}" in stream.getvalue()
        finally:
            _reset_logging()

    def test_404(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/missing")
            assert f"status={resp.status_code}" in stream.getvalue()
        finally:
            _reset_logging()

    def test_500_on_unhandled_exception(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/error")
            assert resp.status_code == 500
            assert "status=500" in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION E — Log contains request duration/latency
# ===========================================================================


class TestLogContainsDuration:
    """Every log entry must include duration_ms >= 0."""

    def test_duration_ms_present(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            output = stream.getvalue()
            match = re.search(r"duration_ms=([0-9.]+)", output)
            assert match is not None, "duration_ms not found in log"
            assert float(match.group(1)) >= 0
        finally:
            _reset_logging()

    def test_slow_endpoint_has_measurable_duration(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/slow")
            output = stream.getvalue()
            match = re.search(r"duration_ms=([0-9.]+)", output)
            assert match is not None
            assert float(match.group(1)) >= 40, (
                f"Expected ~50ms, got {match.group(1)}ms"
            )
        finally:
            _reset_logging()


# ===========================================================================
# SECTION F — Log contains a request ID
# ===========================================================================


class TestLogContainsRequestID:
    """Every log entry must include a request_id that is a valid UUID."""

    def test_request_id_is_valid_uuid(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            output = stream.getvalue()
            match = re.search(r"request_id=([0-9a-f-]+)", output)
            assert match is not None, "request_id not found in log"
            rid = match.group(1)
            parsed = uuid.UUID(rid)
            assert str(parsed) == rid
        finally:
            _reset_logging()

    def test_request_id_in_response_header(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/")
            rid = resp.headers.get("X-Request-ID")
            assert rid is not None, "X-Request-ID header missing"
            parsed = uuid.UUID(rid)
            assert str(parsed) == rid
        finally:
            _reset_logging()

    def test_response_header_matches_log(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/")
            header_rid = resp.headers.get("X-Request-ID", "")
            output = stream.getvalue()
            assert header_rid in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION G — Different requests receive appropriate request IDs
# ===========================================================================


class TestRequestIDsUnique:
    """Each request must get a distinct request ID."""

    def test_two_requests_different_ids(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp1 = client.get("/")
            resp2 = client.get("/health")
            rid1 = resp1.headers.get("X-Request-ID")
            rid2 = resp2.headers.get("X-Request-ID")
            assert rid1 is not None
            assert rid2 is not None
            assert rid1 != rid2
        finally:
            _reset_logging()

    def test_error_request_gets_unique_id(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp_ok = client.get("/")
            resp_err = client.get("/error")
            rid_ok = resp_ok.headers.get("X-Request-ID")
            rid_err = resp_err.headers.get("X-Request-ID")
            assert rid_ok != rid_err
        finally:
            _reset_logging()


# ===========================================================================
# SECTION H — Sensitive headers/tokens are not written to logs
# ===========================================================================


class TestSensitiveDataNotLogged:
    """Authorization tokens and sensitive headers must never appear in logs."""

    def test_authorization_header_not_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            client.get(
                "/",
                headers={"Authorization": f"Bearer {token}"},
            )
            output = stream.getvalue()
            assert token not in output
            assert "Bearer" not in output
        finally:
            _reset_logging()

    def test_cookie_header_not_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get(
                "/",
                headers={"Cookie": "session=secret_value_123"},
            )
            output = stream.getvalue()
            assert "secret_value_123" not in output
            assert "session=" not in output
        finally:
            _reset_logging()

    def test_api_key_header_not_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get(
                "/",
                headers={"X-API-Key": "sk-proj-supersecret"},
            )
            output = stream.getvalue()
            assert "sk-proj-supersecret" not in output
        finally:
            _reset_logging()

    def test_request_body_not_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.post(
                "/items",
                json={"password": "hunter2", "username": "admin"},
            )
            output = stream.getvalue()
            assert "hunter2" not in output
            assert "password" not in output
        finally:
            _reset_logging()

    def test_response_body_not_logged(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            client.get("/")
            output = stream.getvalue()
            assert "Welcome to DToxOut" not in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION I — X-Request-ID response header is present
# ===========================================================================


class TestRequestIDHeader:
    """Every response must carry an X-Request-ID header."""

    def test_root_has_request_id_header(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/")
            assert "X-Request-ID" in resp.headers
        finally:
            _reset_logging()

    def test_404_has_request_id_header(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/missing")
            assert "X-Request-ID" in resp.headers
        finally:
            _reset_logging()

    def test_error_has_request_id_header(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/error")
            assert "X-Request-ID" in resp.headers
        finally:
            _reset_logging()


# ===========================================================================
# SECTION J — Existing behaviour unaffected
# ===========================================================================


class TestExistingBehaviourUnaffected:
    """Middleware must not break routes or alter response bodies."""

    def test_root_returns_expected_body(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/")
            assert resp.json() == {"message": "ok"}
        finally:
            _reset_logging()

    def test_health_returns_expected_body(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.get("/health")
            assert resp.json() == {"status": "healthy"}
        finally:
            _reset_logging()

    def test_post_returns_expected_body(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            client = _make_client()
            resp = client.post("/items")
            assert resp.json() == {"created": True}
        finally:
            _reset_logging()
