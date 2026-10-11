"""
Admin Dashboard business logic service.

All database queries for dashboard analytics live here.
API routes should call this service instead of querying Prisma directly.

Usage from a route handler:

    from app.services.dashboard_service import DashboardService
    from app.database import get_db

    service = DashboardService(db)
    stats = await service.get_dashboard_stats()
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from prisma import Prisma

from app.schemas.dashboard import (
    DashboardStatsResponse,
    EvidenceDistributionResponse,
    EvidenceLevelCount,
    RiskDistributionResponse,
    RiskLevelCount,
)

# Expected risk and evidence level labels.  Any level with zero records
# will still appear in the distribution output with a count of 0 so the
# front-end can render a stable set of chart labels.
_ALL_RISK_LEVELS: list[str] = ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]
_ALL_EVIDENCE_LEVELS: list[str] = ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]

logger = logging.getLogger(__name__)


class DashboardService:
    """Stateless service wrapping all dashboard analytics operations.

    Instantiate once per request (or once at startup if the ``db``
    client is shared) and call its async methods.

        service = DashboardService(db)
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Aggregate statistics
    # ------------------------------------------------------------------

    async def get_dashboard_stats(self) -> DashboardStatsResponse:
        """Return aggregated counts across the entire knowledge base.

        Uses concurrent ``asyncio.gather`` calls for independent count
        queries and Prisma ``group_by`` for distribution aggregation.

        Returns:
            A ``DashboardStatsResponse`` containing entity counts
            and recent-activity figures.
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        results = await asyncio.gather(
            self._db.user.count(),
            self._db.ingredient.count(),
            self._db.ingredientcategory.count(),
            self._db.ingredientbenefit.count(),
            self._db.ingredientalias.count(),
            self._db.safetyprofile.count(),
            self._db.regulation.count(),
            self._db.scientificreference.count(),
            self._db.scan.count(),
            self._db.user.count(where={"createdAt": {"gte": seven_days_ago}}),
            self._db.scan.count(where={"createdAt": {"gte": seven_days_ago}}),
        )

        (
            users,
            ingredients,
            ingredient_categories,
            ingredient_benefits,
            ingredient_aliases,
            safety_profiles,
            regulations,
            scientific_references,
            scans,
            users_last_7_days,
            scans_last_7_days,
        ) = results

        return DashboardStatsResponse(
            users=users,
            ingredients=ingredients,
            ingredient_categories=ingredient_categories,
            ingredient_benefits=ingredient_benefits,
            ingredient_aliases=ingredient_aliases,
            safety_profiles=safety_profiles,
            regulations=regulations,
            scientific_references=scientific_references,
            scans=scans,
            users_last_7_days=users_last_7_days,
            scans_last_7_days=scans_last_7_days,
        )

    # ------------------------------------------------------------------
    # Risk distribution
    # ------------------------------------------------------------------

    async def get_risk_distribution(self) -> RiskDistributionResponse:

        groups = await self._db.safetyprofile.group_by(
            by=["riskLevel"],
            count=True,
        )

        counts: dict[str, int] = {
            "LOW": 0,
            "MODERATE": 0,
            "HIGH": 0,
            "VERY_HIGH": 0,
        }

        total = 0
        for group in groups:
            level = str(group["riskLevel"])
            count = group["_count"]["_all"]
            total += count
            if level in counts:
                counts[level] = count

        return RiskDistributionResponse(
            total=total,
            distribution=[
                RiskLevelCount(risk_level="LOW", count=counts["LOW"]),
                RiskLevelCount(risk_level="MODERATE", count=counts["MODERATE"]),
                RiskLevelCount(risk_level="HIGH", count=counts["HIGH"]),
                RiskLevelCount(risk_level="VERY_HIGH", count=counts["VERY_HIGH"]),
            ],
        )

    # ------------------------------------------------------------------
    # Evidence distribution
    # ------------------------------------------------------------------

    async def get_evidence_distribution(self) -> EvidenceDistributionResponse:

        groups = await self._db.ingredient.group_by(
            by=["evidenceLevel"],
            count=True,
        )

        counts: dict[str, int] = {
            "LOW": 0,
            "MODERATE": 0,
            "HIGH": 0,
            "VERY_HIGH": 0,
        }

        total = 0
        for group in groups:
            level = str(group["evidenceLevel"])
            count = group["_count"]["_all"]
            total += count
            if level in counts:
                counts[level] = count

        return EvidenceDistributionResponse(
            total=total,
            distribution=[
                EvidenceLevelCount(
                    evidence_level="LOW",
                    count=counts["LOW"],
                ),
                EvidenceLevelCount(
                    evidence_level="MODERATE",
                    count=counts["MODERATE"],
                ),
                EvidenceLevelCount(
                    evidence_level="HIGH",
                    count=counts["HIGH"],
                ),
                EvidenceLevelCount(
                    evidence_level="VERY_HIGH",
                    count=counts["VERY_HIGH"],
                ),
            ],
        )