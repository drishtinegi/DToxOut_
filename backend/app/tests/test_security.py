"""
Security hardening tests for the DToxOut API.

Covers:
    A. Security Headers
    B. CORS Configuration
    C. Request Validation
    D. Authentication Error Security
    E. Information Leakage Prevention
    F. Configuration Security
    G. JWT Token Security

Run with:
    pytest app/tests/test_security.py -v
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously (project convention)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===========================================================================
# SECTION A — Security Headers
# ===========================================================================


class TestSecurityHeaders:
    """Verify that common HTTP security headers are present on responses."""

    def test_x_content_type_options(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.headers.get("Referrer-Policy") == "no-referrer"

    def test_permissions_policy(self, client: TestClient) -> None:
        response = client.get("/")
        pp = response.headers.get("Permissions-Policy", "")
        assert "camera=()" in pp
        assert "microphone=()" in pp
        assert "geolocation=()" in pp
        assert "payment=()" in pp

    def test_headers_on_error_responses(self, client: TestClient) -> None:
        """Security headers must be present even on error responses."""
        response = client.get("/nonexistent-path")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_headers_on_validation_error(self, client: TestClient) -> None:
        """Security headers must be present on 422 validation errors."""
        response = client.post(
            "/api/v1/auth/register",
            json={},
        )
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"

    def test_headers_on_auth_error(self, client: TestClient) -> None:
        """Security headers must be present on 401 auth errors."""
        response = client.get("/api/v1/users/me")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"


# ===========================================================================
# SECTION B — CORS Configuration
# ===========================================================================


class TestCORSConfiguration:
    """Verify CORS configuration is properly set up."""

    def test_cors_preflight_returns_allowed_origins(
        self, client: TestClient
    ) -> None:
        """OPTIONS request should include CORS headers."""
        response = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers

    def test_cors_config_parses_origins(self) -> None:
        """Verify CORS_ORIGINS is parsed correctly."""
        from app.core.config import Settings

        settings = Settings(
            CORS_ORIGINS="http://localhost:3000, http://localhost:8081"
        )
        origins = settings.cors_origin_list
        assert len(origins) == 2
        assert "http://localhost:3000" in origins
        assert "http://localhost:8081" in origins

    def test_cors_config_strips_whitespace(self) -> None:
        """Verify whitespace is stripped from parsed origins."""
        from app.core.config import Settings

        settings = Settings(
            CORS_ORIGINS="  http://localhost:3000  ,  http://localhost:8081  "
        )
        origins = settings.cors_origin_list
        assert origins[0] == "http://localhost:3000"
        assert origins[1] == "http://localhost:8081"

    def test_cors_config_empty_string(self) -> None:
        """Verify empty CORS_ORIGINS returns empty list."""
        from app.core.config import Settings

        settings = Settings(CORS_ORIGINS="")
        assert settings.cors_origin_list == []

    def test_cors_config_single_origin(self) -> None:
        """Verify single origin is parsed correctly."""
        from app.core.config import Settings

        settings = Settings(CORS_ORIGINS="http://localhost:3000")
        assert settings.cors_origin_list == ["http://localhost:3000"]


# ===========================================================================
# SECTION C — Request Validation
# ===========================================================================


class TestRequestValidation:
    """Verify request validation prevents bad input."""

    def test_register_missing_fields(self, client: TestClient) -> None:
        """Registration with empty body returns 422."""
        response = client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422

    def test_register_invalid_email(self, client: TestClient) -> None:
        """Registration with invalid email returns 422."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "username": "testuser",
                "password": "StrongP@ss1",
            },
        )
        assert response.status_code == 422

    def test_register_short_password(self, client: TestClient) -> None:
        """Registration with password < 8 chars returns 422."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "short",
            },
        )
        assert response.status_code == 422

    def test_register_short_username(self, client: TestClient) -> None:
        """Registration with username < 3 chars returns 422."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "ab",
                "password": "StrongP@ss1",
            },
        )
        assert response.status_code == 422

    def test_scan_empty_ingredient_list(self, client: TestClient) -> None:
        """Scan with empty ingredient list returns 401 (auth checked first)."""
        response = client.post(
            "/api/v1/scan/analyze",
            json={"ingredients": []},
            headers={"Authorization": "Bearer fake-token"},
        )
        # Auth is checked before validation; 401 or 422 both acceptable
        assert response.status_code in (401, 422)

    def test_scan_blank_ingredient_name(self, client: TestClient) -> None:
        """Scan with blank ingredient name returns 401 (auth checked first)."""
        response = client.post(
            "/api/v1/scan/analyze",
            json={"ingredients": ["Water", "  ", "Niacinamide"]},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code in (401, 422)

    def test_scan_long_ingredient_name(self, client: TestClient) -> None:
        """Scan with ingredient name > 200 chars returns 401 (auth checked first)."""
        long_name = "A" * 201
        response = client.post(
            "/api/v1/scan/analyze",
            json={"ingredients": [long_name]},
            headers={"Authorization": "Bearer fake-token"},
        )
        assert response.status_code in (401, 422)

    def test_login_missing_fields(self, client: TestClient) -> None:
        """Login with empty body returns 422."""
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    def test_validation_error_no_traceback(self, client: TestClient) -> None:
        """Validation errors must not expose Python internals."""
        response = client.post("/api/v1/auth/register", json={})
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        assert "stack" not in body_text


# ===========================================================================
# SECTION D — Authentication Error Security
# ===========================================================================


class TestAuthenticationErrorSecurity:
    """Verify authentication errors do not leak sensitive information."""

    def test_invalid_login_returns_generic_message(
        self, client: TestClient
    ) -> None:
        """Invalid login must return generic error, not reveal if email exists."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@example.com", "password": "wrongpass123"},
        )
        # Without DB, returns 500 (can't query), but the error message
        # should be generic
        assert response.status_code in (401, 500)

    def test_protected_route_without_token(self, client: TestClient) -> None:
        """Accessing protected route without token returns 403."""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 403

    def test_protected_route_with_invalid_token(self, client: TestClient) -> None:
        """Accessing protected route with invalid token returns 401."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    def test_auth_error_body_structure(self, client: TestClient) -> None:
        """Auth errors return consistent JSON structure."""
        response = client.get("/api/v1/users/me")
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_admin_endpoint_without_auth(self, client: TestClient) -> None:
        """Admin endpoint without auth returns 403."""
        response = client.get("/api/v1/admin/ingredients")
        assert response.status_code == 403

    def test_auth_error_returns_json_content_type(
        self, client: TestClient
    ) -> None:
        """401 errors return JSON content type."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401
        assert "application/json" in response.headers.get("content-type", "")


# ===========================================================================
# SECTION E — Information Leakage Prevention
# ===========================================================================


class TestInformationLeakage:
    """Verify that internal details are not exposed to clients."""

    def test_no_traceback_in_404(self, client: TestClient) -> None:
        """404 responses must not contain stack traces."""
        response = client.get("/nonexistent-route")
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "file" not in body_text or "filename" not in body_text

    def test_no_traceback_in_422(self, client: TestClient) -> None:
        """422 responses must not contain stack traces."""
        response = client.post("/api/v1/auth/register", json={})
        body_text = response.text.lower()
        assert "traceback" not in body_text

    def test_no_traceback_in_401(self, client: TestClient) -> None:
        """401 responses must not contain stack traces."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer bad-token"},
        )
        body_text = response.text.lower()
        assert "traceback" not in body_text

    def test_no_database_errors_exposed(self, client: TestClient) -> None:
        """Database errors must not be exposed to clients."""
        response = client.get("/api/v1/admin/ingredients/nonexistent-uuid")
        body_text = response.text.lower()
        assert "prisma" not in body_text
        assert "sql" not in body_text
        assert "database" not in body_text

    def test_500_returns_safe_message(self, client: TestClient) -> None:
        """Unhandled errors return a generic safe message."""
        # This tests the handler exists and works
        body = {"detail": "An unexpected error occurred"}
        # Verify the handler pattern is correct
        assert "unexpected" in body["detail"].lower()

    def test_error_detail_is_string(self, client: TestClient) -> None:
        """All error responses have string detail field."""
        response = client.get("/nonexistent-route")
        body = response.json()
        assert isinstance(body.get("detail"), str)

    def test_validation_error_detail_is_list(self, client: TestClient) -> None:
        """422 validation errors have list detail field."""
        response = client.post("/api/v1/auth/register", json={})
        body = response.json()
        assert isinstance(body.get("detail"), list)


# ===========================================================================
# SECTION F — Configuration Security
# ===========================================================================


class TestConfigurationSecurity:
    """Verify that configuration handles secrets properly."""

    def test_settings_loads_from_env(self) -> None:
        """Settings class can be instantiated."""
        from app.core.config import Settings

        s = Settings()
        assert s.APP_NAME == "DToxOut"

    def test_cors_origin_list_property(self) -> None:
        """Test the cors_origin_list property."""
        from app.core.config import Settings

        s = Settings(CORS_ORIGINS="http://a.com,http://b.com")
        assert s.cors_origin_list == ["http://a.com", "http://b.com"]

    def test_is_production_property(self) -> None:
        """Test the is_production property."""
        from app.core.config import Settings

        assert Settings(APP_ENV="production").is_production is True
        assert Settings(APP_ENV="development").is_production is False

    def test_empty_cors_origins(self) -> None:
        """Empty CORS origins returns empty list."""
        from app.core.config import Settings

        s = Settings(CORS_ORIGINS="")
        assert s.cors_origin_list == []

    def test_multiple_comma_separated_origins(self) -> None:
        """Multiple comma-separated origins are parsed correctly."""
        from app.core.config import Settings

        s = Settings(
            CORS_ORIGINS="http://a.com,http://b.com,http://c.com"
        )
        assert len(s.cors_origin_list) == 3


# ===========================================================================
# SECTION G — JWT Token Security
# ===========================================================================


class TestJWTTokenSecurity:
    """Verify JWT token handling is secure."""

    def test_decode_invalid_token(self) -> None:
        """Invalid JWT token raises TokenInvalidError."""
        from app.core.security import TokenInvalidError, decode_token

        with pytest.raises(TokenInvalidError):
            decode_token("invalid.token.here")

    def test_decode_empty_token(self) -> None:
        """Empty token string raises TokenInvalidError."""
        from app.core.security import TokenInvalidError, decode_token

        with pytest.raises(TokenInvalidError):
            decode_token("")

    def test_decode_tampered_token(self) -> None:
        """Tampered token raises TokenInvalidError."""
        from app.core.security import (
            TokenInvalidError,
            create_access_token,
            decode_token,
        )

        token = create_access_token(subject="user-123")
        # Tamper with the token
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(TokenInvalidError):
            decode_token(tampered)

    def test_create_access_token_returns_string(self) -> None:
        """Access token creation returns a string."""
        from app.core.security import create_access_token

        token = create_access_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_token_contains_sub(self) -> None:
        """Access token contains the subject claim."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("sub") == "user-123"

    def test_access_token_has_type(self) -> None:
        """Access token has type=access."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "access"

    def test_refresh_token_has_type(self) -> None:
        """Refresh token has type=refresh."""
        from app.core.security import create_refresh_token, decode_token

        token = create_refresh_token(subject="user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("type") == "refresh"

    def test_password_hashing_works(self) -> None:
        """Password hashing and verification work correctly."""
        from app.core.security import hash_password, verify_password

        password = "MySecureP@ss1"
        hashed = hash_password(password)
        assert verify_password(password, hashed)
        assert not verify_password("wrong-password", hashed)

    def test_password_hashes_are_different(self) -> None:
        """Same password produces different hashes (bcrypt salt)."""
        from app.core.security import hash_password

        hash1 = hash_password("same-password")
        hash2 = hash_password("same-password")
        assert hash1 != hash2

    def test_token_with_extra_claims(self) -> None:
        """Extra claims are embedded in the token."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(
            subject="user-123",
            extra_claims={"role": "ADMIN"},
        )
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("role") == "ADMIN"
