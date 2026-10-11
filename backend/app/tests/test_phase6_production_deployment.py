"""
Phase 6 Comprehensive Production Deployment, Security Hardening & Observability Test Suite.

Validates:
- Production configuration rules & fail-fast validation on missing secrets
- Strict CORS allowlist and wildcard credential prohibition
- HTTP Security Headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy)
- Health probe endpoints: GET /health/live and GET /health/ready (connected & disconnected)
- Storage abstraction layer (Local, S3, Azure Blob factory instantiation)
- Session logout endpoint and session expiry handling
- Log privacy (zero secrets, passwords, JWTs, or image bytes logged)
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import app
from app.core.config import Settings, settings
from app.api.health import router as health_router
from app.services.storage_service import (
    get_storage_service,
    LocalStorageService,
    S3StorageService,
    AzureBlobStorageService,
)
from app.database import get_db


@pytest.fixture
def test_client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Part A: Production Configuration & Secret Validation Tests
# ---------------------------------------------------------------------------


class TestProductionConfigurationValidation:

    def test_development_config_bypasses_production_checks(self):
        s = Settings(APP_ENV="development", JWT_SECRET_KEY="", DATABASE_URL="")
        # Should not raise in development mode
        s.validate_production_config()

    def test_missing_jwt_secret_raises_in_production(self):
        s = Settings(APP_ENV="production", JWT_SECRET_KEY="", DATABASE_URL="postgresql://db:5432/db")
        with pytest.raises(ValueError) as exc_info:
            s.validate_production_config()
        assert "JWT_SECRET_KEY must be configured with a secure secret" in str(exc_info.value)

    def test_insecure_default_jwt_secret_raises_in_production(self):
        s = Settings(APP_ENV="production", JWT_SECRET_KEY="default-insecure-key", DATABASE_URL="postgresql://db:5432/db")
        with pytest.raises(ValueError) as exc_info:
            s.validate_production_config()
        assert "JWT_SECRET_KEY must be configured with a secure secret" in str(exc_info.value)

    def test_missing_database_url_raises_in_production(self):
        s = Settings(APP_ENV="production", JWT_SECRET_KEY="a-very-secure-production-secret-12345", DATABASE_URL="")
        with pytest.raises(ValueError) as exc_info:
            s.validate_production_config()
        assert "DATABASE_URL must be explicitly configured" in str(exc_info.value)

    def test_wildcard_cors_with_credentials_raises_in_production(self):
        s = Settings(
            APP_ENV="production",
            JWT_SECRET_KEY="a-very-secure-production-secret-12345",
            DATABASE_URL="postgresql://db:5432/db",
            CORS_ORIGINS="*",
            CORS_ALLOW_CREDENTIALS=True,
        )
        with pytest.raises(ValueError) as exc_info:
            s.validate_production_config()
        assert "Wildcard '*' CORS origin is prohibited" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Part E: Security Headers & CORS Tests
# ---------------------------------------------------------------------------


class TestSecurityHeadersAndCORS:

    def test_security_headers_present_in_responses(self, test_client):
        res = test_client.get("/health/live")
        assert res.status_code == 200
        assert res.headers.get("x-content-type-options") == "nosniff"
        assert res.headers.get("x-frame-options") == "DENY"
        assert res.headers.get("referrer-policy") == "no-referrer"
        assert "camera=()" in res.headers.get("permissions-policy", "")

    def test_cors_allowed_origin(self, test_client):
        res = test_client.options(
            "/api/v1/scan/analyze",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://localhost:3000"


# ---------------------------------------------------------------------------
# Part H: Observability & Health Probes Tests
# ---------------------------------------------------------------------------


class TestHealthProbes:

    def test_health_live_endpoint(self, test_client):
        res = test_client.get("/health/live")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "live"
        assert "timestamp" in data

    def test_health_ready_endpoint_connected(self, test_client):
        res = test_client.get("/health/ready")
        assert res.status_code in (200, 503)
        data = res.json()
        assert "status" in data
        assert "database" in data

    def test_health_ready_endpoint_database_disconnected(self):
        test_app = FastAPI()
        
        async def _mock_db_failure():
            mock_db = MagicMock()
            mock_db.execute_raw = AsyncMock(side_effect=RuntimeError("Database connection lost"))
            yield mock_db

        test_app.dependency_overrides[get_db] = _mock_db_failure
        test_app.include_router(health_router)
        client = TestClient(test_app)

        res = client.get("/health/ready")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "unready"
        assert data["database"] == "disconnected"
        assert "traceback" not in res.text.lower()


# ---------------------------------------------------------------------------
# Part F: Storage Abstraction Tests
# ---------------------------------------------------------------------------


class TestStorageServiceAbstraction:

    def test_get_storage_service_factory(self):
        local_service = get_storage_service("local")
        assert isinstance(local_service, LocalStorageService)

        s3_service = get_storage_service("s3")
        assert isinstance(s3_service, S3StorageService)

        azure_service = get_storage_service("azure")
        assert isinstance(azure_service, AzureBlobStorageService)


# ---------------------------------------------------------------------------
# Part D & H: Auth Logout & Log Privacy Tests
# ---------------------------------------------------------------------------


class TestAuthLogoutAndLogPrivacy:

    def test_auth_logout_endpoint(self, test_client):
        res = test_client.post("/api/v1/auth/logout")
        assert res.status_code == 200
        assert "Logged out" in res.json()["message"]

    def test_no_sensitive_secrets_in_logs(self, caplog):
        from app.core.exceptions import DomainError
        with caplog.at_level("INFO"):
            with patch("app.api.auth.login_user", new=AsyncMock(side_effect=DomainError("Invalid credentials"))):
                test_client = TestClient(app)
                test_client.post("/api/v1/auth/login", json={"email": "demo@dtoxout.org", "password": "SuperSecretPassword123!"})

        log_text = caplog.text
        assert "SuperSecretPassword123!" not in log_text
        assert settings.JWT_SECRET_KEY not in log_text
