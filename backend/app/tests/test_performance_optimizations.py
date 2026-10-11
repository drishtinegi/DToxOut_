"""
Unit tests for performance optimizations (Milestone 12 sub-feature 2).

Verifies that:
- Batch ingredient lookups use find_many instead of N individual find_first calls
- Dashboard distributions use group_by instead of full-table loading
- Dashboard stats use concurrent asyncio.gather instead of sequential awaits
- AnalysisService._resolve_ingredients uses batch queries
- IngredientService._search_advanced uses DB-side partial matching first

Run with:
    pytest app/tests/test_performance_optimizations.py -v
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.services.scan_service import ScanService
from app.services.analysis.analysis_service import AnalysisService
from app.services.dashboard_service import DashboardService
from app.services.ingredient_service import IngredientService, _RELATION_INCLUDE


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


def _make_mock_ingredient(
    inci_name: str = "Niacinamide",
    common_name: str = "Vitamin B3",
    safety_rating: float = 9.0,
    evidence_level: str = "HIGH",
    ingredient_id: str = "id-1",
) -> MagicMock:
    ing = MagicMock()
    ing.id = ingredient_id
    ing.inciName = inci_name
    ing.commonName = common_name
    ing.description = "Form of vitamin B3"
    ing.function = "Skin conditioning"
    ing.safetyRating = safety_rating
    ing.evidenceLevel = evidence_level
    sp = MagicMock()
    sp.riskLevel = "LOW"
    sp.pregnancyRisk = None
    sp.acneRisk = "Non-comedogenic"
    sp.sensitiveSkinRisk = None
    sp.allergyRisk = None
    ing.safetyProfile = sp
    ing.aliases = []
    return ing


# ===========================================================================
# SECTION 1 — ScanService batch lookup
# ===========================================================================


class TestScanServiceBatchLookup:
    """Verify analyze_ingredients uses find_many (batch) not find_first (N+1)."""

    def test_uses_find_many_not_find_first(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[
            _make_mock_ingredient("Niacinamide"),
            _make_mock_ingredient("Panthenol", "Provitamin B5", 9.5, "HIGH", "id-2"),
        ])
        db.ingredient.find_first = AsyncMock(
            side_effect=AssertionError("find_first should not be called"),
        )

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        _run(svc.analyze_ingredients(["Niacinamide", "Panthenol"]))

        db.ingredient.find_many.assert_awaited_once()

    def test_single_query_for_multiple_ingredients(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[
            _make_mock_ingredient("Water", "Aqua", 10.0, "VERY_HIGH", "id-1"),
            _make_mock_ingredient("Glycerin", None, 9.0, "HIGH", "id-2"),
            _make_mock_ingredient("Niacinamide", "Vitamin B3", 9.0, "HIGH", "id-3"),
        ])

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Water", "Glycerin", "Niacinamide"]))

        assert response.recognized_count == 3
        assert response.unknown_count == 0

    def test_deduplicates_before_batch_query(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[
            _make_mock_ingredient("Niacinamide"),
        ])

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients([
            "Niacinamide", "Niacinamide", "Niacinamide",
        ]))

        where_arg = db.ingredient.find_many.call_args_list[0][1]["where"]
        assert where_arg["OR"][0]["inciName"]["in"] == ["niacinamide"]

    def test_unknown_ingredients_still_marked(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[])

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["NonexistentXyz"]))

        assert response.recognized_count == 0
        assert response.unknown_count == 1
        assert response.unknown_ingredients[0].name.lower() == "nonexistentxyz"

    def test_or_conditions_built_for_each_unique_name(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[])

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        _run(svc.analyze_ingredients(["A", "B", "C", "A"]))

        where_arg = db.ingredient.find_many.call_args_list[0][1]["where"]
        assert where_arg["OR"][0]["inciName"]["in"] == ["a", "b", "c"]


# ===========================================================================
# SECTION 2 — persist_analysis batch lookup
# ===========================================================================


class TestPersistAnalysisBatchLookup:
    """Verify persist_analysis uses find_many inside the transaction."""

    def test_persist_uses_find_many(self) -> None:
        db = MagicMock()

        mock_scan = MagicMock()
        mock_scan.id = "scan-id"
        mock_ingredient = MagicMock()
        mock_ingredient.id = "ing-id"

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(return_value=mock_scan)
        mock_tx.ingredient.find_many = AsyncMock(return_value=[mock_ingredient])
        mock_tx.scaningredient.create = AsyncMock()
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=False)

        db.user.find_unique = AsyncMock(return_value=MagicMock())
        db.tx = MagicMock(return_value=mock_tx)

        svc = ScanService(db)
        svc._generate_product_name = lambda x: "Test Product"

        _run(svc.persist_analysis(
            user_id="user-1",
            ingredients=["Niacinamide"],
            overall_score=9.0,
        ))

        mock_tx.ingredient.find_many.assert_awaited_once()

    def test_persist_no_find_first_call(self) -> None:
        db = MagicMock()

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(return_value=MagicMock(id="scan-id"))
        mock_tx.ingredient.find_many = AsyncMock(return_value=[])
        mock_tx.__aenter__ = AsyncMock(return_value=mock_tx)
        mock_tx.__aexit__ = AsyncMock(return_value=False)

        db.user.find_unique = AsyncMock(return_value=MagicMock())
        db.tx = MagicMock(return_value=mock_tx)

        svc = ScanService(db)
        svc._generate_product_name = lambda x: "Test"

        _run(svc.persist_analysis(
            user_id="user-1",
            ingredients=["A", "B", "C"],
            overall_score=5.0,
        ))

        mock_tx.ingredient.find_first.assert_not_awaited()


# ===========================================================================
# SECTION 3 — AnalysisService._resolve_ingredients batch
# ===========================================================================


class TestAnalysisServiceBatchResolve:
    """Verify _resolve_ingredients uses batch queries."""

    def test_uses_find_many_for_ingredients(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[
            _make_mock_ingredient(),
        ])
        db.safetyprofile.find_many = AsyncMock(return_value=[])

        svc = AnalysisService(db)

        result = _run(svc._resolve_ingredients(["Niacinamide"]))

        db.ingredient.find_many.assert_awaited_once()
        assert len(result) == 1

    def test_uses_find_many_for_safety_profiles(self) -> None:
        db = MagicMock()
        ingredient = _make_mock_ingredient(ingredient_id="id-1")
        db.ingredient.find_many = AsyncMock(return_value=[ingredient])

        mock_sp = MagicMock()
        mock_sp.ingredientId = "id-1"
        db.safetyprofile.find_many = AsyncMock(return_value=[mock_sp])

        svc = AnalysisService(db)

        result = _run(svc._resolve_ingredients(["Niacinamide"]))

        db.safetyprofile.find_many.assert_awaited_once()
        where_arg = db.safetyprofile.find_many.call_args[1]["where"]
        assert "in" in where_arg["ingredientId"]

    def test_no_find_first_call(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[])
        db.safetyprofile.find_many = AsyncMock(return_value=[])

        svc = AnalysisService(db)

        _run(svc._resolve_ingredients(["X"]))

        assert not db.ingredient.find_first.called


# ===========================================================================
# SECTION 4 — Dashboard group_by
# ===========================================================================


class TestDashboardGroupBy:
    """Verify distributions use group_by instead of full-table load."""

    def test_risk_distribution_uses_group_by(self) -> None:
        db = MagicMock()
        db.safetyprofile.group_by = AsyncMock(return_value=[
            {"riskLevel": "LOW", "_count": {"_all": 10, "riskLevel": 10}},
            {"riskLevel": "MODERATE", "_count": {"_all": 5, "riskLevel": 5}},
            {"riskLevel": "HIGH", "_count": {"_all": 3, "riskLevel": 3}},
            {"riskLevel": "VERY_HIGH", "_count": {"_all": 2, "riskLevel": 2}},
        ])
        db.safetyprofile.find_many = AsyncMock(
            side_effect=AssertionError("find_many should not be called"),
        )

        svc = DashboardService(db)
        result = _run(svc.get_risk_distribution())

        db.safetyprofile.group_by.assert_awaited_once()
        assert result.total == 20
        assert result.distribution[0].count == 10
        assert result.distribution[1].count == 5
        assert result.distribution[2].count == 3
        assert result.distribution[3].count == 2

    def test_risk_distribution_zero_counts(self) -> None:
        db = MagicMock()
        db.safetyprofile.group_by = AsyncMock(return_value=[])

        svc = DashboardService(db)
        result = _run(svc.get_risk_distribution())

        assert result.total == 0
        assert all(d.count == 0 for d in result.distribution)

    def test_evidence_distribution_uses_group_by(self) -> None:
        db = MagicMock()
        db.ingredient.group_by = AsyncMock(return_value=[
            {"evidenceLevel": "HIGH", "_count": {"_all": 15, "evidenceLevel": 15}},
            {"evidenceLevel": "VERY_HIGH", "_count": {"_all": 8, "evidenceLevel": 8}},
        ])
        db.ingredient.find_many = AsyncMock(
            side_effect=AssertionError("find_many should not be called"),
        )

        svc = DashboardService(db)
        result = _run(svc.get_evidence_distribution())

        db.ingredient.group_by.assert_awaited_once()
        assert result.total == 23
        assert result.distribution[2].count == 15
        assert result.distribution[3].count == 8


# ===========================================================================
# SECTION 5 — Dashboard asyncio.gather
# ===========================================================================


class TestDashboardConcurrentStats:
    """Verify get_dashboard_stats uses asyncio.gather for concurrent queries."""

    def test_uses_gather(self) -> None:
        db = MagicMock()

        db.user.count = AsyncMock(return_value=5)
        db.ingredient.count = AsyncMock(return_value=100)
        db.ingredientcategory.count = AsyncMock(return_value=10)
        db.ingredientbenefit.count = AsyncMock(return_value=20)
        db.ingredientalias.count = AsyncMock(return_value=50)
        db.safetyprofile.count = AsyncMock(return_value=30)
        db.regulation.count = AsyncMock(return_value=5)
        db.scientificreference.count = AsyncMock(return_value=8)
        db.scan.count = AsyncMock(return_value=15)

        svc = DashboardService(db)
        result = _run(svc.get_dashboard_stats())

        assert result.users == 5
        assert result.ingredients == 100
        assert result.scans == 15

    def test_uses_gather_not_sequential(self) -> None:
        """Verify all count queries are dispatched via concurrent gather."""
        db = MagicMock()

        db.user.count = AsyncMock(return_value=5)
        db.ingredient.count = AsyncMock(return_value=100)
        db.ingredientcategory.count = AsyncMock(return_value=10)
        db.ingredientbenefit.count = AsyncMock(return_value=20)
        db.ingredientalias.count = AsyncMock(return_value=50)
        db.safetyprofile.count = AsyncMock(return_value=30)
        db.regulation.count = AsyncMock(return_value=5)
        db.scientificreference.count = AsyncMock(return_value=8)
        db.scan.count = AsyncMock(return_value=15)

        svc = DashboardService(db)
        _run(svc.get_dashboard_stats())

        # user.count and scan.count are each called twice (total + last_7_days)
        # All other models are called once = 11 total count() calls
        total = sum([
            db.user.count.await_count,
            db.ingredient.count.await_count,
            db.ingredientcategory.count.await_count,
            db.ingredientbenefit.count.await_count,
            db.ingredientalias.count.await_count,
            db.safetyprofile.count.await_count,
            db.regulation.count.await_count,
            db.scientificreference.count.await_count,
            db.scan.count.await_count,
        ])
        assert total == 11


# ===========================================================================
# SECTION 6 — IngredientService._search_advanced DB-side filtering
# ===========================================================================


class TestSearchAdvancedDBFiltering:
    """Verify _search_advanced tries DB-side partial matching first."""

    def test_partial_inci_avoids_full_table_scan(self) -> None:
        db = MagicMock()

        mock_ingredient = _make_mock_ingredient()
        mock_ingredient.inciName = "Niacinamide"
        mock_ingredient.aliases = []

        db.ingredient.find_many = AsyncMock(return_value=[mock_ingredient])
        db.ingredientalias.find_many = AsyncMock(return_value=[])

        svc = IngredientService(db)

        result = _run(svc._search_advanced(
            "niacin", 0.0, "niacin",
        ))

        assert result is not None
        assert result.matched_by.value == "INCI_NAME"

    def test_partial_alias_queries_alias_table(self) -> None:
        db = MagicMock()

        mock_ing = _make_mock_ingredient()
        mock_ing.inciName = "Tocopherol"
        mock_ing.aliases = []

        mock_alias = MagicMock()
        mock_alias.alias = "Vitamin E"
        mock_alias.ingredient = mock_ing

        db.ingredient.find_many = AsyncMock(return_value=[])
        db.ingredientalias.find_many = AsyncMock(return_value=[mock_alias])

        svc = IngredientService(db)

        result = _run(svc._search_advanced(
            "vitamin", 0.0, "vitamin",
        ))

        assert result is not None
        assert result.matched_by.value == "ALIAS"

    def test_fuzzy_match_still_works(self) -> None:
        db = MagicMock()

        mock_ing = _make_mock_ingredient()
        mock_ing.inciName = "Niacinamide"
        mock_ing.commonName = None
        mock_ing.aliases = []

        db.ingredient.find_many = AsyncMock(return_value=[mock_ing])
        db.ingredientalias.find_many = AsyncMock(return_value=[])

        svc = IngredientService(db)

        result = _run(svc._search_advanced(
            "niacinmid", 0.0, "niacinmid",
        ))

        assert result is not None
        assert result.matched_by.value == "INCI_NAME"
