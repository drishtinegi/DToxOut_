"""
Admin-only Dashboard API routes.

Every endpoint in this router requires ADMIN role authorization.
Dashboard analytics delegate to DashboardService --
Prisma is never accessed directly from route handlers.
"""

import logging

from fastapi import APIRouter, Depends, status
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import require_admin
from app.database import get_db
from app.schemas.dashboard import (
    DashboardStatsResponse,
    EvidenceDistributionResponse,
    RiskDistributionResponse,
)
from app.services.dashboard_service import DashboardService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependency: provide a DashboardService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> DashboardService:
    """Build a DashboardService per request using the active DB client."""
    return DashboardService(db)


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=DashboardStatsResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_stats(
    current_user: User = Depends(require_admin),
    service: DashboardService = Depends(_get_service),
) -> DashboardStatsResponse:
    """Return aggregated statistics for the admin dashboard.

    Admin only.  Returns entity counts across the knowledge base
    and recent-activity metrics for the last 7 days.

    Returns **200** on success.
    """
    return await service.get_dashboard_stats()


@router.get(
    "/risk-distribution",
    response_model=RiskDistributionResponse,
    status_code=status.HTTP_200_OK,
)
async def get_risk_distribution(
    current_user: User = Depends(require_admin),
    service: DashboardService = Depends(_get_service),
) -> RiskDistributionResponse:
    """Return the distribution of ingredients across risk levels.

    Admin only.  Returns per-level counts suitable for pie or bar charts.

    Returns **200** on success.
    """
    return await service.get_risk_distribution()


@router.get(
    "/evidence-distribution",
    response_model=EvidenceDistributionResponse,
    status_code=status.HTTP_200_OK,
)
async def get_evidence_distribution(
    current_user: User = Depends(require_admin),
    service: DashboardService = Depends(_get_service),
) -> EvidenceDistributionResponse:
    """Return the distribution of ingredients across evidence levels.

    Admin only.  Returns per-level counts suitable for pie or bar charts.

    Returns **200** on success.
    """
    return await service.get_evidence_distribution()
