"""
DToxOut API — Main Application Entry Point.

Initializes FastAPI, registers routers, and wires the database
lifespan so that the Prisma connection pool is opened on startup
and closed on shutdown.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import DomainError
from app.core.logging import configure_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.rate_limiting import setup_rate_limiting
from app.database.client import lifespan
from app.api.safety_profile import router as safety_profile_router
from app.api.regulation import router as regulation_router
from app.api.scientific_reference import router as scientific_reference_router
from app.api.scan import router as scan_router
from app.api.dashboard import router as dashboard_router
from app.api.search import router as search_router
from app.api.scan_history import router as scan_history_router
from app.api.knowledge import router as knowledge_router

# ---------------------------------------------------------------------------
# Structured logging — must be configured before any logger is used
# ---------------------------------------------------------------------------

configure_logging(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Lightweight middleware that adds common HTTP security headers.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: no-referrer
    - Permissions-Policy: restrictive default policy
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if settings.is_production and settings.HSTS_MAX_AGE > 0:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE}; includeSubDomains"
            )
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )
        return response

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Application lifespan wrapper.

    Delegates database connect / disconnect to the reusable lifespan
    defined in ``app.database.client`` while keeping a single place
    to add future startup / shutdown hooks.
    """
    # --- startup ---
    # Fail fast on insecure production config (weak JWT secret, missing DB, ...)
    settings.validate_production_config()
    async with lifespan(app):
        yield
        # --- shutdown ---


app = FastAPI(
    title="DToxOut API",
    version="1.0.0",
    description="Cosmetic ingredient safety analysis API",
    lifespan=app_lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    openapi_tags=[
        {"name": "health", "description": "Health-check endpoints"},
        {"name": "auth", "description": "Authentication and registration"},
        {"name": "users", "description": "User profile endpoints"},
        {"name": "admin", "description": "Admin-only management endpoints"},
        {"name": "Scan", "description": "Scan analysis endpoints"},
        {"name": "Scan History", "description": "User scan history endpoints"},
        {"name": "search", "description": "Ingredient search endpoints"},
        {"name": "knowledge", "description": "AI knowledge engine endpoints"},
    ],
)


# ---------------------------------------------------------------------------
# Security Headers
# ---------------------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Request/Response Logging (captures request lifecycle)
# ---------------------------------------------------------------------------

app.add_middleware(RequestLoggingMiddleware)


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

setup_rate_limiting(app)


# ---------------------------------------------------------------------------
# CORS Configuration (Outermost middleware — wraps all responses & errors)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS.split(","),
    allow_headers=settings.CORS_ALLOW_HEADERS.split(","),
)



# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Translate service-layer DomainError exceptions into JSON responses.

    Every DomainError carries its own ``status_code`` and ``detail``.
    The full exception chain is logged server-side for debugging; only
    the user-safe ``detail`` message is returned to the client.
    """
    logger.warning(
        "Domain error on %s %s: [%s] %s",
        request.method,
        request.url.path,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Pass through FastAPI/Starlette HTTPException with consistent JSON body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": str(exc.detail)},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 422 with the standard Pydantic validation error body."""
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — logs the full traceback but returns a safe generic message."""
    logger.exception(
        "Unhandled error on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred"},
    )

# ---- Routers ----

# Health endpoints remain unversioned
app.include_router(health_router)

# Versioned API (primary)
app.include_router(api_v1_router)

# Backward-compatible unversioned routes (deprecated — use /api/v1/ instead)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(scan_router)
app.include_router(safety_profile_router)
app.include_router(regulation_router)
app.include_router(scientific_reference_router)
app.include_router(dashboard_router)
app.include_router(search_router)
app.include_router(scan_history_router)
app.include_router(knowledge_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint — returns a welcome message."""
    return {"message": "Welcome to DToxOut API"}


@app.get("/api/version", tags=["version"])
async def api_version() -> dict[str, str]:
    """Return the current API version and available versions."""
    return {
        "current": "v1",
        "available": "v1",
        "docs": "/docs" if settings.api_docs_enabled else "disabled",
    }
