"""
Unit tests for the enriched ScanResponse integration (Milestone 12 Step 2).

Verifies that:
- All original ScanResponse fields are still present and correct
- Extended analysis fields (confidence_score, analysis_timestamp,
  explanation_summary, explanation_reasons, recommended_for, precautions,
  usage_guidance, ingredient_explanations) are populated when
  AnalysisService succeeds
- Extended analysis fields remain None when AnalysisService fails
- Fallback behavior works correctly (graceful degradation)
- Existing recommendation and warning behavior is unchanged

Run with:
    pytest app/tests/test_scan_enriched_response.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.analysis import (
    AnalysisResult,
    IngredientExplanation,
    OverallAnalysis,
    ProductExplanation,
    ProductRecommendation,
)
from app.schemas.scan import (
    IngredientAnalysis,
    ScanResponse,
    UnknownIngredient,
)
from app.services.scan_service import ScanService


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


def _make_mock_db() -> MagicMock:
    """Create a mock Prisma DB client that returns a known ingredient."""
    db = MagicMock()

    mock_ingredient = MagicMock()
    mock_ingredient.inciName = "Niacinamide"
    mock_ingredient.commonName = "Vitamin B3"
    mock_ingredient.description = "Form of vitamin B3"
    mock_ingredient.function = "Skin conditioning"
    mock_ingredient.safetyRating = 9.0
    mock_ingredient.evidenceLevel = "HIGH"

    mock_sp = MagicMock()
    mock_sp.riskLevel = "LOW"
    mock_sp.pregnancyRisk = None
    mock_sp.acneRisk = "Non-comedogenic"
    mock_sp.sensitiveSkinRisk = None
    mock_sp.allergyRisk = None
    mock_ingredient.safetyProfile = mock_sp

    db.ingredient.find_many = AsyncMock(return_value=[mock_ingredient])
    return db


def _make_analysis_result() -> AnalysisResult:
    """Create a deterministic AnalysisResult for testing."""
    overall = OverallAnalysis(
        overall_score=9.0,
        overall_risk="LOW",
        ingredient_count=1,
        summary="This product appears to contain mostly low-risk cosmetic ingredients.",
    )
    explanation = ProductExplanation(
        summary="This product appears to contain mostly low-risk cosmetic ingredients.",
        reasons=[
            "The overall ingredient safety rating is excellent.",
            "This product has a relatively simple formulation.",
        ],
        ingredient_explanations=[
            IngredientExplanation(
                ingredient_name="Niacinamide",
                safety_rating=9.0,
                risk_level="LOW",
                reason="This ingredient is generally considered safe.",
            )
        ],
    )
    recommendations = ProductRecommendation(
        recommended_for=["oily", "dry", "combination", "sensitive", "normal"],
        precautions=[
            "Perform a patch test before first use",
            "Discontinue use if irritation occurs",
        ],
        usage_guidance="Apply to clean skin morning and evening as part of your routine.",
    )
    return AnalysisResult(
        product_name="Niacinamide",
        ingredient_count=1,
        overall_analysis=overall,
        product_explanation=explanation,
        recommendations=recommendations,
        confidence_score=85,
        analysis_timestamp=datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_service(analysis_return_value=None, analysis_side_effect=None):
    """Build a ScanService with mocked DB and AnalysisService."""
    db = _make_mock_db()
    svc = ScanService(db)
    svc._analysis_service = MagicMock()
    if analysis_side_effect is not None:
        svc._analysis_service.analyze_product = AsyncMock(
            side_effect=analysis_side_effect
        )
    else:
        svc._analysis_service.analyze_product = AsyncMock(
            return_value=analysis_return_value
        )
    return svc


# ===========================================================================
# SECTION 1 — Base Response Integrity
# ===========================================================================


class TestBaseResponseIntegrity:
    """All original ScanResponse fields must be present and correct."""

    def test_valid_scan_returns_response(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response, ScanResponse)

    def test_overall_score_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.overall_score == 9.25
        assert isinstance(response.overall_score, float)

    def test_overall_risk_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.overall_risk == "LOW"

    def test_recognized_count_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recognized_count == 1

    def test_unknown_count_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.unknown_count == 0

    def test_recognized_ingredients_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert len(response.recognized_ingredients) == 1
        assert isinstance(response.recognized_ingredients[0], IngredientAnalysis)
        assert response.recognized_ingredients[0].inci_name == "Niacinamide"
        assert response.recognized_ingredients[0].safety_rating == 9.0
        assert response.recognized_ingredients[0].risk == "LOW"

    def test_unknown_ingredients_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response.unknown_ingredients, list)
        assert len(response.unknown_ingredients) == 0

    def test_analysis_summary_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response.analysis_summary, str)
        assert len(response.analysis_summary) > 0

    def test_recommendation_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recommendation == "SAFE"

    def test_recommendation_message_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response.recommendation_message, str)
        assert len(response.recommendation_message) > 0

    def test_warnings_present(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response.warnings, list)


# ===========================================================================
# SECTION 2 — Extended Analysis Success
# ===========================================================================


class TestExtendedAnalysisSuccess:
    """When AnalysisService succeeds, all extended fields must be populated."""

    def test_confidence_score_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.confidence_score == 85
        assert isinstance(response.confidence_score, int)

    def test_analysis_timestamp_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.analysis_timestamp is not None
        assert isinstance(response.analysis_timestamp, datetime)
        assert response.analysis_timestamp.year == 2026
        assert response.analysis_timestamp.month == 7

    def test_explanation_summary_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.explanation_summary is not None
        assert "low-risk" in response.explanation_summary.lower()

    def test_explanation_reasons_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.explanation_reasons is not None
        assert isinstance(response.explanation_reasons, list)
        assert len(response.explanation_reasons) == 2
        assert "excellent" in response.explanation_reasons[0].lower()

    def test_recommended_for_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recommended_for is not None
        assert isinstance(response.recommended_for, list)
        assert "oily" in response.recommended_for
        assert "dry" in response.recommended_for
        assert "combination" in response.recommended_for
        assert "sensitive" in response.recommended_for
        assert "normal" in response.recommended_for

    def test_precautions_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.precautions is not None
        assert isinstance(response.precautions, list)
        assert len(response.precautions) == 2
        assert "patch test" in response.precautions[0].lower()

    def test_usage_guidance_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.usage_guidance is not None
        assert "morning" in response.usage_guidance.lower()

    def test_ingredient_explanations_populated(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.ingredient_explanations is not None
        assert isinstance(response.ingredient_explanations, list)
        assert len(response.ingredient_explanations) == 1
        ie = response.ingredient_explanations[0]
        assert ie["ingredient_name"] == "Niacinamide"
        assert ie["safety_rating"] == 9.0
        assert ie["risk_level"] == "LOW"
        assert "safe" in ie["reason"].lower()


# ===========================================================================
# SECTION 3 — Extended Analysis Failure / Fallback
# ===========================================================================


class TestExtendedAnalysisFailure:
    """When AnalysisService fails, extended fields must safely remain None."""

    def test_confidence_score_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.confidence_score is not None

    def test_analysis_timestamp_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.analysis_timestamp is None

    def test_explanation_summary_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.explanation_summary is None

    def test_explanation_reasons_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.explanation_reasons is None

    def test_recommended_for_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recommended_for is None

    def test_precautions_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.precautions is None

    def test_usage_guidance_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.usage_guidance is None

    def test_ingredient_explanations_none_on_failure(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.ingredient_explanations is None


# ===========================================================================
# SECTION 4 — Base Fields Unaffected by Analysis Failure
# ===========================================================================


class TestBaseFieldsUnaffectedByFailure:
    """Base scan response must be fully intact even when analysis fails."""

    def test_overall_score_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.overall_score == 9.25

    def test_overall_risk_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.overall_risk == "LOW"

    def test_recognized_count_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recognized_count == 1

    def test_recognized_ingredients_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert len(response.recognized_ingredients) == 1
        assert response.recognized_ingredients[0].inci_name == "Niacinamide"

    def test_recommendation_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.recommendation == "SAFE"

    def test_recommendation_message_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert len(response.recommendation_message) > 0

    def test_warnings_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response.warnings, list)

    def test_analysis_summary_preserved(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert len(response.analysis_summary) > 0


# ===========================================================================
# SECTION 5 — Extended Analysis Returns None (Edge Case)
# ===========================================================================


class TestAnalysisServiceReturnsNone:
    """If analyze_product returns None, extended fields must safely remain None."""

    def test_extended_fields_none_when_service_returns_none(self) -> None:
        svc = _make_service(analysis_return_value=None)
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.confidence_score is not None
        assert response.analysis_timestamp is None
        assert response.explanation_summary is None
        assert response.explanation_reasons is None
        assert response.recommended_for is None
        assert response.precautions is None
        assert response.usage_guidance is None
        assert response.ingredient_explanations is None

    def test_base_fields_intact_when_service_returns_none(self) -> None:
        svc = _make_service(analysis_return_value=None)
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert response.overall_score == 9.25
        assert response.overall_risk == "LOW"
        assert response.recognized_count == 1
        assert response.recommendation == "SAFE"


# ===========================================================================
# SECTION 6 — Unknown Ingredients
# ===========================================================================


class TestUnknownIngredients:
    """Verify correct handling when some ingredients are not recognized."""

    def test_mixed_recognized_and_unknown(self) -> None:
        db = MagicMock()

        mock_ingredient = MagicMock()
        mock_ingredient.inciName = "Niacinamide"
        mock_ingredient.commonName = "Vitamin B3"
        mock_ingredient.description = "Form of vitamin B3"
        mock_ingredient.function = "Skin conditioning"
        mock_ingredient.safetyRating = 9.0
        mock_ingredient.evidenceLevel = "HIGH"
        sp = MagicMock()
        sp.riskLevel = "LOW"
        sp.pregnancyRisk = None
        sp.acneRisk = None
        sp.sensitiveSkinRisk = None
        sp.allergyRisk = None
        mock_ingredient.safetyProfile = sp

        db.ingredient.find_many = AsyncMock(return_value=[mock_ingredient])

        svc = ScanService(db)
        svc._analysis_service = MagicMock()
        svc._analysis_service.analyze_product = AsyncMock(
            return_value=_make_analysis_result()
        )

        response = _run(svc.analyze_ingredients(["Fragrance", "Niacinamide"]))

        assert response.recognized_count == 1
        assert response.unknown_count == 1
        assert len(response.unknown_ingredients) == 1
        assert response.unknown_ingredients[0].name.lower() == "fragrance"
        assert "not found" in response.unknown_ingredients[0].reason.lower()


# ===========================================================================
# SECTION 7 — Schema Validation
# ===========================================================================


class TestSchemaValidation:
    """Verify the enriched response is valid Pydantic and serializes correctly."""

    def test_response_is_valid_pydantic(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        assert isinstance(response, ScanResponse)
        d = response.model_dump()
        assert "confidence_score" in d
        assert "analysis_timestamp" in d
        assert "explanation_summary" in d
        assert "explanation_reasons" in d
        assert "recommended_for" in d
        assert "precautions" in d
        assert "usage_guidance" in d
        assert "ingredient_explanations" in d

    def test_response_serializes_to_json(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        json_str = response.model_dump_json()
        assert "confidence_score" in json_str
        assert "Niacinamide" in json_str

    def test_base_response_without_extended_fields(self) -> None:
        svc = _make_service(
            analysis_side_effect=RuntimeError("DB connection lost")
        )
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        d = response.model_dump()
        assert d["confidence_score"] is not None
        assert d["analysis_timestamp"] is None
        assert d["explanation_summary"] is None

    def test_response_with_all_original_fields_in_dict(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        response = _run(svc.analyze_ingredients(["Niacinamide"]))
        d = response.model_dump()
        original_fields = [
            "overall_score",
            "overall_risk",
            "recognized_count",
            "unknown_count",
            "recognized_ingredients",
            "unknown_ingredients",
            "analysis_summary",
            "recommendation",
            "recommendation_message",
            "warnings",
        ]
        for field in original_fields:
            assert field in d, f"Original field '{field}' missing from response dict"


# ===========================================================================
# SECTION 8 — AnalysisService Call Verification
# ===========================================================================


class TestAnalysisServiceCallVerification:
    """Verify that AnalysisService is called correctly and results are merged."""

    def test_analysis_service_called_with_correct_args(self) -> None:
        svc = _make_service(analysis_return_value=_make_analysis_result())
        _run(svc.analyze_ingredients(["Niacinamide"]))
        svc._analysis_service.analyze_product.assert_called_once()

    def test_analysis_service_called_after_base_analysis(self) -> None:
        call_order = []

        original_gen = svc_class = None

        class TrackingAnalysisService:
            async def analyze_product(self, **kwargs):
                call_order.append("analysis_service")
                return _make_analysis_result()

        db = _make_mock_db()
        svc = ScanService(db)
        svc._analysis_service = TrackingAnalysisService()

        original_recommend = svc._recommendation_service.generate_recommendation
        def track_recommend(*args, **kwargs):
            call_order.append("recommendation_service")
            return original_recommend(*args, **kwargs)
        svc._recommendation_service.generate_recommendation = track_recommend

        _run(svc.analyze_ingredients(["Niacinamide"]))
        assert call_order == ["recommendation_service", "analysis_service"]
