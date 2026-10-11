"""
Health-check probes module for container orchestrators, load balancers, and monitoring.

Exposes separate liveness (/health/live) and readiness (/health/ready) probes.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from prisma import Prisma
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness check — confirms the API process is running."""
    return {"status": "healthy"}


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness probe — verifies the web application is alive and responding."""
    return {
        "status": "live",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def health_ready(db: Prisma = Depends(get_db)) -> JSONResponse:
    """Readiness probe — verifies required external dependencies (database connectivity).

    Returns:
        200 OK with status="ready" if database is reachable.
        503 Service Unavailable with status="unready" if database is down.
    """
    try:
        await db.execute_raw("SELECT 1")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ready",
                "database": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unready",
                "database": "disconnected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


@router.get("/health/database")
async def database_health(db: Prisma = Depends(get_db)) -> JSONResponse:
    """Legacy database readiness probe (backward compatibility)."""
    return await health_ready(db)
