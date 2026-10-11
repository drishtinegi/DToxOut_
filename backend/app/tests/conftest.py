"""
Shared test fixtures for the DToxOut test suite.

Provides a ``client`` fixture that gives each test a FastAPI TestClient
backed by a lightweight test app that skips the database lifespan.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.regulation import router as regulation_router
from app.api.safety_profile import router as safety_profile_router
from app.api.scan import router as scan_router
from app.api.scan_history import router as scan_history_router
from app.api.scientific_reference import router as scientific_reference_router
from app.api.search import router as search_router
from app.api.users import router as users_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import DomainError


# ---------------------------------------------------------------------------
# Exception handlers — must mirror main.py registrations
# ---------------------------------------------------------------------------


async def _domain_error_handler(request, exc: DomainError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


async def _http_exception_handler(request, exc: StarletteHTTPException):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
    )


async def _validation_error_handler(request, exc: RequestValidationError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


async def _unhandled_error_handler(request, exc: Exception):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )


# ---------------------------------------------------------------------------
# Security Headers Middleware (test version)
# ---------------------------------------------------------------------------


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers middleware for the test app."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )
        return response


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _build_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing (no DB lifespan)."""
    test_app = FastAPI(title="DToxOut Test")
    test_app.add_exception_handler(DomainError, _domain_error_handler)
    test_app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    test_app.add_exception_handler(RequestValidationError, _validation_error_handler)
    test_app.add_exception_handler(Exception, _unhandled_error_handler)

    # Add CORS middleware
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS.split(","),
        allow_headers=settings.CORS_ALLOW_HEADERS.split(","),
    )

    # Add security headers middleware
    test_app.add_middleware(_SecurityHeadersMiddleware)

    # Health endpoints remain unversioned
    test_app.include_router(health_router)

    # Versioned API (primary)
    test_app.include_router(api_v1_router)

    # Backward-compatible unversioned routes
    test_app.include_router(auth_router)
    test_app.include_router(users_router)
    test_app.include_router(admin_router)
    test_app.include_router(scan_router)
    test_app.include_router(safety_profile_router)
    test_app.include_router(regulation_router)
    test_app.include_router(scientific_reference_router)
    test_app.include_router(dashboard_router)
    test_app.include_router(search_router)
    test_app.include_router(scan_history_router)
    test_app.include_router(knowledge_router)

    @test_app.get("/")
    async def root():
        return {"message": "Welcome to DToxOut API"}

    @test_app.get("/api/version", tags=["version"])
    async def api_version():
        return {"current": "v1", "available": "v1", "docs": "/docs"}

    return test_app


@pytest.fixture()
def client() -> TestClient:
    """Provide a fresh TestClient for each test.

    The client uses a lightweight test app that registers the same
    routers and exception handlers as the production app, but does
    NOT connect to the database.
    """
    app = _build_test_app()
    return TestClient(app, raise_server_exceptions=False)
