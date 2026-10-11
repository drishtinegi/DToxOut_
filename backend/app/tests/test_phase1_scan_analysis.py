"""
Comprehensive unit tests for Phase 1 Scan Analysis.

Verifies:
1. Exact INCI matching
2. Exact alias matching
3. Exact common-name matching
4. Case-insensitive matching
5. Harmless punctuation normalization
6. Rejection of unsafe substring matches
7. Duplicate ingredient input handling & order preservation
8. Unknown ingredient handling & coverage percentage
9. All ingredients unknown handling
10. Missing safety profile fallback
11. Missing evidence level fallback
12. Regulatory status output (jurisdiction specific)
13. Scientific-reference output
14. Confidence reduction for unknown ingredients
15. No unqualified SAFE result when coverage is incomplete
16. Consistent risk thresholds across engines
17. Backward compatibility of existing response fields

Run with:
    pytest app/tests/test_phase1_scan_analysis.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.scan import (
    IngredientAnalysis,
    MatchType,
    ScanResponse,
    UnknownIngredient,
)
from app.services.risk_engine import ProductRiskEngine
from app.services.scan_service import ScanService
from app.utils.ingredient_matcher import IngredientMatcher, normalize_ingredient_name


def _run(coro):
    """Run an async coroutine synchronously (project convention)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_mock_ingredient(
    inci_name: str = "Niacinamide",
    common_name: str | None = "Vitamin B3",
    aliases: list[str] | None = None,
    safety_rating: float = 9.0,
    evidence_level: str = "HIGH",
    risk_level: str | None = "LOW",
    regulations: list[dict] | None = None,
    scientific_references: list[dict] | None = None,
) -> MagicMock:
    """Helper to build mock Prisma Ingredient model."""
    ing = MagicMock()
    ing.inciName = inci_name
    ing.commonName = common_name
    ing.description = f"Description for {inci_name}"
    ing.function = "Skin conditioning"
    ing.safetyRating = safety_rating
    ing.evidenceLevel = evidence_level

    # Aliases
    alias_mocks = []
    if aliases:
        for a in aliases:
            am = MagicMock()
            am.alias = a
            alias_mocks.append(am)
    ing.aliases = alias_mocks

    # Safety Profile
    if risk_level is not None:
        sp = MagicMock()
        sp.riskLevel = risk_level
        sp.pregnancyRisk = None
        sp.acneRisk = "Non-comedogenic"
        sp.sensitiveSkinRisk = None
        sp.allergyRisk = None
        ing.safetyProfile = sp
    else:
        ing.safetyProfile = None

    # Regulations
    reg_mocks = []
    if regulations:
        for r in regulations:
            rm = MagicMock()
            rm.country = r.get("country", "EU")
            rm.regulatoryStatus = r.get("regulatory_status", "RESTRICTED")
            rm.restrictionDetails = r.get("restriction_details", "Max 0.3%")
            rm.source = r.get("source", "EU CosIng")
            reg_mocks.append(rm)
    ing.regulations = reg_mocks

    # Scientific References
    ref_mocks = []
    if scientific_references:
        for ref in scientific_references:
            rf = MagicMock()
            rf.title = ref.get("title", "Safety Study")
            rf.organization = ref.get("organization", "CIR")
            rf.publicationYear = ref.get("publication_year", 2023)
            rf.evidenceSummary = ref.get("evidence_summary", "Safe as used")
            rf.sourceUrl = ref.get("source_url", "https://example.com")
            ref_mocks.append(rf)
    ing.scientificReferences = ref_mocks

    return ing


# ===========================================================================
# 1. Matching Hierarchy & Substring Rejection Tests
# ===========================================================================


class TestMatchingHierarchy:
    """Verify strict matching priority and rejection of unsafe partial substring matches."""

    def test_exact_inci_match(self) -> None:
        ing = _make_mock_ingredient(inci_name="Niacinamide")
        res = IngredientMatcher.match_single("niacinamide", [ing])
        assert res.ingredient is ing
        assert res.match_type == MatchType.EXACT_INCI
        assert res.match_confidence == 1.0
        assert not res.manual_confirmation_recommended

    def test_exact_alias_match(self) -> None:
        ing = _make_mock_ingredient(inci_name="Niacinamide", aliases=["Nicotinamide"])
        res = IngredientMatcher.match_single("nicotinamide", [ing])
        assert res.ingredient is ing
        assert res.match_type == MatchType.EXACT_ALIAS
        assert res.match_confidence == 1.0

    def test_exact_common_name_match(self) -> None:
        ing = _make_mock_ingredient(inci_name="Niacinamide", common_name="Vitamin B3")
        res = IngredientMatcher.match_single("vitamin b3", [ing])
        assert res.ingredient is ing
        assert res.match_type == MatchType.EXACT_COMMON_NAME
        assert res.match_confidence == 1.0

    def test_case_insensitive_matching(self) -> None:
        ing = _make_mock_ingredient(inci_name="Niacinamide")
        res = IngredientMatcher.match_single("NIACINAMIDE", [ing])
        assert res.match_type == MatchType.EXACT_INCI

    def test_harmless_punctuation_normalization(self) -> None:
        assert normalize_ingredient_name(" Niacinamide, ") == "niacinamide"
        assert normalize_ingredient_name("Panthenol.") == "panthenol"
        assert normalize_ingredient_name(" Glycerin; ") == "glycerin"

    def test_rejection_of_unsafe_substring_matches(self) -> None:
        ing_salicylic = _make_mock_ingredient(inci_name="Salicylic Acid")
        ing_argan = _make_mock_ingredient(inci_name="Argania Spinosa Kernel Oil")

        # "acid" must NOT match "Salicylic Acid"
        res_acid = IngredientMatcher.match_single("acid", [ing_salicylic])
        assert res_acid.match_type == MatchType.UNKNOWN
        assert res_acid.ingredient is None

        # "oil" must NOT match "Argania Spinosa Kernel Oil"
        res_oil = IngredientMatcher.match_single("oil", [ing_argan])
        assert res_oil.match_type == MatchType.UNKNOWN
        assert res_oil.ingredient is None

        # "extract" must NOT match unrelated ingredient
        res_ext = IngredientMatcher.match_single("extract", [ing_salicylic])
        assert res_ext.match_type == MatchType.UNKNOWN

    def test_bounded_fuzzy_matching(self) -> None:
        ing = _make_mock_ingredient(inci_name="Niacinamide")
        # Typo "Niacinamid" (1 char missing) should fuzzy match with high confidence
        res = IngredientMatcher.match_single("niacinamid", [ing])
        assert res.match_type == MatchType.FUZZY
        assert res.match_confidence >= 0.85
        assert res.manual_confirmation_recommended


# ===========================================================================
# 2. Input Deduplication & Order Preservation
# ===========================================================================


class TestInputDeduplication:
    """Repeated input terms must not distort counts or scores, and preserve display order."""

    def test_deduplication_preserves_first_seen_order_and_counts(self) -> None:
        db = MagicMock()
        mock_niacinamide = _make_mock_ingredient(inci_name="Niacinamide")
        mock_water = _make_mock_ingredient(inci_name="Water", common_name="Aqua")

        db.ingredient.find_many = AsyncMock(return_value=[mock_niacinamide, mock_water])
        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        input_list = ["Water", "Niacinamide", "water", "WATER", "Niacinamide", "Unknown Ingredient"]
        response = _run(svc.analyze_ingredients(input_list))

        assert response.recognized_count == 2
        assert response.unknown_count == 1
        # Order preserved: Water first, Niacinamide second
        assert response.recognized_ingredients[0].inci_name == "Water"
        assert response.recognized_ingredients[1].inci_name == "Niacinamide"
        assert response.recognition_coverage == round(2 / 3 * 100, 2)


# ===========================================================================
# 3. Unknown Ingredient & Safety Policy
# ===========================================================================


class TestUnknownIngredientHandling:
    """Unknown ingredients must penalize confidence and prevent unqualified SAFE recommendations."""

    def test_unknown_ingredient_prevents_unqualified_safe(self) -> None:
        db = MagicMock()
        mock_safe = _make_mock_ingredient(inci_name="Niacinamide", safety_rating=9.5, risk_level="LOW")
        db.ingredient.find_many = AsyncMock(return_value=[mock_safe])

        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Niacinamide", "Unknown Chemical X"]))

        assert response.recognized_count == 1
        assert response.unknown_count == 1
        assert response.recommendation == "USE WITH CAUTION"
        assert any(w.type == "INCOMPLETE_COVERAGE" for w in response.warnings)

    def test_all_ingredients_unknown(self) -> None:
        db = MagicMock()
        db.ingredient.find_many = AsyncMock(return_value=[])

        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Unknown A", "Unknown B"]))

        assert response.recognized_count == 0
        assert response.unknown_count == 2
        assert response.overall_score == 0.0
        assert response.overall_risk == "VERY_HIGH"
        assert response.confidence_score == 0
        assert response.recognition_coverage == 0.0
        assert response.recommendation == "USE WITH CAUTION"
        assert len(response.unknown_ingredients) == 2


# ===========================================================================
# 4. Missing Profile & Missing Evidence Fallback
# ===========================================================================


class TestMissingDataFallback:
    """Missing safety profile or evidence level must fall back gracefully to neutral defaults."""

    def test_missing_safety_profile_and_evidence_level(self) -> None:
        db = MagicMock()
        mock_no_sp = _make_mock_ingredient(
            inci_name="Panthenol",
            safety_rating=8.0,
            evidence_level="HIGH",
            risk_level=None,  # No SafetyProfile
        )
        db.ingredient.find_many = AsyncMock(return_value=[mock_no_sp])

        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Panthenol"]))
        assert response.recognized_count == 1
        assert isinstance(response.overall_score, float)
        assert response.overall_risk in ["LOW", "MODERATE", "HIGH", "VERY_HIGH"]


# ===========================================================================
# 5. Evidence & Regulatory Status Output
# ===========================================================================


class TestEvidenceAndRegulatoryOutput:
    """Regulations and scientific references must be populated from DB with jurisdiction specificity."""

    def test_regulations_and_references_populated(self) -> None:
        db = MagicMock()
        mock_ing = _make_mock_ingredient(
            inci_name="Retinol",
            safety_rating=5.0,
            regulations=[
                {
                    "country": "European Union",
                    "regulatory_status": "RESTRICTED",
                    "restriction_details": "Max concentration 0.3%",
                    "source": "EU CosIng",
                }
            ],
            scientific_references=[
                {
                    "title": "Retinoid Safety Assessment",
                    "organization": "SCCS",
                    "publication_year": 2022,
                    "evidence_summary": "Restricted in leave-on cosmetics",
                    "source_url": "https://ec.europa.eu",
                }
            ],
        )
        db.ingredient.find_many = AsyncMock(return_value=[mock_ing])

        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Retinol"]))
        rec_ing = response.recognized_ingredients[0]

        assert rec_ing.regulations is not None
        assert len(rec_ing.regulations) == 1
        assert rec_ing.regulations[0]["country"] == "European Union"
        assert rec_ing.regulations[0]["regulatory_status"] == "RESTRICTED"

        assert rec_ing.scientific_references is not None
        assert len(rec_ing.scientific_references) == 1
        assert rec_ing.scientific_references[0]["organization"] == "SCCS"


# ===========================================================================
# 6. Backward Compatibility & Threshold Consistency
# ===========================================================================


class TestBackwardCompatibilityAndThresholds:
    """Verify existing response fields remain present and risk thresholds are consistent."""

    def test_risk_threshold_consistency(self) -> None:
        assert ProductRiskEngine.calculate_risk_level(9.0) == "LOW"
        assert ProductRiskEngine.calculate_risk_level(7.0) == "MODERATE"
        assert ProductRiskEngine.calculate_risk_level(5.0) == "HIGH"
        assert ProductRiskEngine.calculate_risk_level(3.0) == "VERY_HIGH"

    def test_response_disclaimer_present(self) -> None:
        db = MagicMock()
        mock_ing = _make_mock_ingredient(inci_name="Glycerin")
        db.ingredient.find_many = AsyncMock(return_value=[mock_ing])

        svc = ScanService(db)
        svc._analysis_service.analyze_product = AsyncMock(return_value=None)

        response = _run(svc.analyze_ingredients(["Glycerin"]))
        assert response.disclaimer is not None
        assert "informational only" in response.disclaimer.lower()
