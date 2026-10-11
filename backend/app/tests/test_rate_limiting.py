"""
Rate limiting tests for the DToxOut API.

Verifies:
    A. Rate-limit configuration
    B. Auth endpoint rate limiting (5/minute)
    C. Scan endpoint rate limiting (10/minute)
    D. Search endpoint rate limiting (30/minute)
    E. 429 response safety (non-leaking)
    F. Versioned and unversioned route rate limiting

All tests use a dedicated test app with rate limiting enabled.
Unique ``X-Forwarded-For`` IPs per test avoid counter collisions.

Run with:
    pytest app/tests/test_rate_limiting.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prisma.models import User

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.scan import router as scan_router
from app.api.search import router as search_router
from app.api.v1.router import api_v1_router
from app.core.dependencies import get_current_user
from app.middleware.rate_limiting import setup_rate_limiting


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _mock_get_current_user() -> User:
    """Return a fake authenticated user (no DB required)."""
    user = MagicMock(spec=User)
    user.id = "00000000-0000-0000-0000-000000000001"
    user.role = "USER"
    return user


# ---------------------------------------------------------------------------
# Test app factory — mirrors production but skips the DB lifespan
# ---------------------------------------------------------------------------

def _build_rate_limit_test_app() -> FastAPI:
    """Create a FastAPI app with rate limiting enabled for testing."""
    app = FastAPI(title="DToxOut Rate Limit Test")
    setup_rate_limiting(app)

    # Override auth dependency so protected endpoints work without a DB
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    # Unversioned routes
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(scan_router)
    app.include_router(search_router)

    # Versioned routes (primary)
    app.include_router(api_v1_router)

    return app


@pytest.fixture()
def rl_client() -> TestClient:
    """Provide a test client with rate limiting active."""
    app = _build_rate_limit_test_app()
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# SECTION A — Rate-Limit Configuration
# ===========================================================================


class TestRateLimitConfiguration:
    """Verify that rate-limit settings are properly configured."""

    def test_default_rate_limit_configured(self) -> None:
        from app.core.config import Settings

        s = Settings()
        assert s.RATE_LIMIT_DEFAULT == "60/minute"

    def test_auth_rate_limit_configured(self) -> None:
        from app.core.config import Settings

        s = Settings()
        assert s.RATE_LIMIT_AUTH == "5/minute"

    def test_scan_rate_limit_configured(self) -> None:
        from app.core.config import Settings

        s = Settings()
        assert s.RATE_LIMIT_SCAN == "10/minute"

    def test_search_rate_limit_configured(self) -> None:
        from app.core.config import Settings

        s = Settings()
        assert s.RATE_LIMIT_SEARCH == "30/minute"

    def test_rate_limits_overridable_via_env(self) -> None:
        """Rate limits can be overridden via environment variables."""
        from app.core.config import Settings

        s = Settings(
            RATE_LIMIT_DEFAULT="100/minute",
            RATE_LIMIT_AUTH="3/minute",
            RATE_LIMIT_SCAN="5/minute",
            RATE_LIMIT_SEARCH="20/minute",
        )
        assert s.RATE_LIMIT_DEFAULT == "100/minute"
        assert s.RATE_LIMIT_AUTH == "3/minute"
        assert s.RATE_LIMIT_SCAN == "5/minute"
        assert s.RATE_LIMIT_SEARCH == "20/minute"


# ===========================================================================
# SECTION B — Auth Endpoint Rate Limiting (5/minute)
# ===========================================================================


class TestAuthEndpointRateLimiting:
    """Verify rate limiting on POST /auth/register and /auth/login (5/min)."""

    def test_register_below_limit_succeeds(self, rl_client: TestClient) -> None:
        """Requests below the auth rate limit should NOT return 429."""
        for i in range(2):
            response = rl_client.post(
                "/auth/register",
                json={
                    "email": f"below{i}@example.com",
                    "username": f"belowuser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.10.0.1"},
            )
            assert response.status_code != 429

    def test_register_exceeding_limit_returns_429(
        self, rl_client: TestClient
    ) -> None:
        """Exceeding the register rate limit (5/min) returns 429."""
        for i in range(6):
            response = rl_client.post(
                "/auth/register",
                json={
                    "email": f"exceed{i}@example.com",
                    "username": f"exceeduser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.10.1.1"},
            )
        assert response.status_code == 429

    def test_login_exceeding_limit_returns_429(
        self, rl_client: TestClient
    ) -> None:
        """Exceeding the login rate limit (5/min) returns 429."""
        for i in range(6):
            response = rl_client.post(
                "/auth/login",
                json={
                    "email": f"login{i}@example.com",
                    "password": "wrongpass",
                },
                headers={"X-Forwarded-For": "10.10.2.1"},
            )
        assert response.status_code == 429


# ===========================================================================
# SECTION C — Scan Endpoint Rate Limiting (10/minute)
# ===========================================================================


class TestScanEndpointRateLimiting:
    """Verify rate limiting on POST /scan/analyze (10/min)."""

    def test_scan_exceeding_limit_returns_429(
        self, rl_client: TestClient
    ) -> None:
        """Exceeding the scan rate limit (10/min) returns 429.

        Note: auth dependency is mocked via dependency_overrides so the
        rate limit check is reached before the endpoint body runs.
        """
        for i in range(11):
            response = rl_client.post(
                "/scan/analyze",
                json={"ingredients": ["Water"]},
                headers={
                    "Authorization": "Bearer fake-token",
                    "X-Forwarded-For": "10.20.1.1",
                },
            )
        assert response.status_code == 429

    def test_scan_below_limit_succeeds(self, rl_client: TestClient) -> None:
        """Requests below the scan rate limit should NOT return 429."""
        for i in range(3):
            response = rl_client.post(
                "/scan/analyze",
                json={"ingredients": ["Water"]},
                headers={
                    "Authorization": "Bearer fake-token",
                    "X-Forwarded-For": "10.20.0.1",
                },
            )
            assert response.status_code != 429


# ===========================================================================
# SECTION D — Search Endpoint Rate Limiting (30/minute)
# ===========================================================================


class TestSearchEndpointRateLimiting:
    """Verify rate limiting on search endpoints (30/min)."""

    def test_single_search_exceeding_limit_returns_429(
        self, rl_client: TestClient
    ) -> None:
        """Exceeding the single-search rate limit (30/min) returns 429."""
        for i in range(31):
            response = rl_client.get(
                "/search/ingredient",
                params={"query": f"ingredient{i}"},
                headers={"X-Forwarded-For": "10.30.1.1"},
            )
        assert response.status_code == 429

    def test_single_search_below_limit_succeeds(
        self, rl_client: TestClient
    ) -> None:
        """Requests below the search rate limit should NOT return 429."""
        for i in range(3):
            response = rl_client.get(
                "/search/ingredient",
                params={"query": f"safe{i}"},
                headers={"X-Forwarded-For": "10.30.0.1"},
            )
            assert response.status_code != 429

    def test_bulk_search_exceeding_limit_returns_429(
        self, rl_client: TestClient
    ) -> None:
        """Exceeding the bulk-search rate limit (30/min) returns 429."""
        for i in range(31):
            response = rl_client.post(
                "/search/ingredients",
                json={"ingredients": [f"ing{i}"]},
                headers={"X-Forwarded-For": "10.30.2.1"},
            )
        assert response.status_code == 429


# ===========================================================================
# SECTION E — 429 Response Safety
# ===========================================================================


class TestRateLimitResponseSafety:
    """Verify 429 responses are safe and properly formatted."""

    def _trigger_429(
        self, rl_client: TestClient, ip: str = "10.40.1.1"
    ) -> TestClient.response_class:
        """Helper: send 6 register requests to trigger the 429."""
        response = None
        for i in range(6):
            response = rl_client.post(
                "/auth/register",
                json={
                    "email": f"safety{i}@example.com",
                    "username": f"safetyuser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": ip},
            )
        return response

    def test_429_returns_json_content_type(
        self, rl_client: TestClient
    ) -> None:
        """429 response has JSON content type."""
        response = self._trigger_429(rl_client, ip="10.40.1.1")
        assert response.status_code == 429
        assert "application/json" in response.headers.get("content-type", "")

    def test_429_body_has_detail_field(
        self, rl_client: TestClient
    ) -> None:
        """429 response body contains a 'detail' string field."""
        response = self._trigger_429(rl_client, ip="10.40.2.1")
        assert response.status_code == 429
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_429_no_sensitive_info_exposed(
        self, rl_client: TestClient
    ) -> None:
        """429 response must not expose internal details."""
        response = self._trigger_429(rl_client, ip="10.40.3.1")
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "internal" not in body_text
        assert "password" not in body_text
        assert "secret" not in body_text
        assert "database" not in body_text

    def test_429_returns_with_consistent_json_structure(
        self, rl_client: TestClient
    ) -> None:
        """429 response follows the same JSON structure as other errors."""
        response = self._trigger_429(rl_client, ip="10.40.4.1")
        assert response.status_code == 429
        body = response.json()
        assert "detail" in body
        assert body["detail"] == "Rate limit exceeded. Please try again later."


# ===========================================================================
# SECTION F — Versioned and Unversioned Route Rate Limiting
# ===========================================================================


class TestVersionedAndUnversionedRateLimiting:
    """Verify rate limiting works on both /api/v1/... and unversioned paths."""

    def test_versioned_auth_is_rate_limited(
        self, rl_client: TestClient
    ) -> None:
        """POST /api/v1/auth/register is rate limited."""
        for i in range(6):
            response = rl_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"ver{i}@example.com",
                    "username": f"veruser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.50.1.1"},
            )
        assert response.status_code == 429

    def test_unversioned_auth_is_rate_limited(
        self, rl_client: TestClient
    ) -> None:
        """POST /auth/register (unversioned) is rate limited."""
        for i in range(6):
            response = rl_client.post(
                "/auth/register",
                json={
                    "email": f"unv{i}@example.com",
                    "username": f"unvuser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.50.2.1"},
            )
        assert response.status_code == 429

    def test_both_versioned_and_unversioned_independently_rate_limited(
        self, rl_client: TestClient
    ) -> None:
        """Both /auth/register and /api/v1/auth/register are rate limited.

        Each path is independently rate-limited — exceeding the limit
        on one path returns 429 for that path.
        """
        # Exhaust limit on versioned path
        for i in range(6):
            response = rl_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"ver{i}@example.com",
                    "username": f"veruser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.50.3.1"},
            )
        assert response.status_code == 429

        # Exhaust limit on unversioned path (different IP to be safe)
        for i in range(6):
            response = rl_client.post(
                "/auth/register",
                json={
                    "email": f"unv{i}@example.com",
                    "username": f"unvuser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.50.3.2"},
            )
        assert response.status_code == 429

    def test_health_endpoint_not_rate_limited(
        self, rl_client: TestClient
    ) -> None:
        """Health endpoint has no rate limit decorator — should never 429."""
        for _ in range(10):
            response = rl_client.get("/health")
            assert response.status_code != 429

    def test_different_ips_have_separate_counters(
        self, rl_client: TestClient
    ) -> None:
        """Different client IPs get independent rate limit counters."""
        # Exhaust limit from IP A
        for i in range(6):
            rl_client.post(
                "/auth/register",
                json={
                    "email": f"ipA{i}@example.com",
                    "username": f"ipAuser{i}",
                    "password": "StrongP@ss1",
                },
                headers={"X-Forwarded-For": "10.60.1.1"},
            )

        # IP B should still be under the limit
        response = rl_client.post(
            "/auth/register",
            json={
                "email": "ipB@example.com",
                "username": "ipBuser",
                "password": "StrongP@ss1",
            },
            headers={"X-Forwarded-For": "10.60.2.1"},
        )
        assert response.status_code != 429
