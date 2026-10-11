"""
Unit tests for the Recommendation Engine service.

Covers:
    - Overall risk-level to recommendation mapping (all 4 levels + fallback)
    - Input normalization (lowercase, whitespace)
    - Unknown risk-level fallback behavior
    - Warning generation for each warning type (PREGNANCY, ACNE,
      SENSITIVE_SKIN, ALLERGY)
    - Warning suppression for None / missing profile fields
    - Negation-aware matching (prevents false-positive warnings)
    - Warning deduplication for duplicate (type, ingredient) pairs
    - Deterministic output ordering
    - Severity derivation from ingredient risk level

Run with:
    pytest app/tests/test_recommendation_service.py -v
"""

from __future__ import annotations

import pytest

from app.services.recommendation_service import RecommendationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> RecommendationService:
    """Provide a fresh RecommendationService instance for each test."""
    return RecommendationService()


# ===========================================================================
# SECTION 1 — Risk-Level to Recommendation Mapping
# ===========================================================================


class TestRiskLevelMapping:
    """Verify that each valid risk level maps to the correct recommendation."""

    def test_low_maps_to_safe(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("LOW", [])
        assert result.recommendation == "SAFE"
        assert "low overall ingredient risk" in result.recommendation_message.lower()

    def test_moderate_maps_to_use_with_caution(
        self, service: RecommendationService,
    ) -> None:
        result = service.generate_recommendation("MODERATE", [])
        assert result.recommendation == "USE WITH CAUTION"
        assert "caution" in result.recommendation_message.lower()

    def test_high_maps_to_high_risk(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("HIGH", [])
        assert result.recommendation == "HIGH RISK"
        assert "elevated risk" in result.recommendation_message.lower()

    def test_very_high_maps_to_avoid(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("VERY_HIGH", [])
        assert result.recommendation == "AVOID"
        assert "very high risk" in result.recommendation_message.lower()


# ===========================================================================
# SECTION 2 — Input Normalization
# ===========================================================================


class TestInputNormalization:
    """Verify that risk-level strings are normalized correctly."""

    def test_lowercase_low(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("low", [])
        assert result.recommendation == "SAFE"

    def test_lowercase_moderate(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("moderate", [])
        assert result.recommendation == "USE WITH CAUTION"

    def test_lowercase_high(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("high", [])
        assert result.recommendation == "HIGH RISK"

    def test_lowercase_very_high(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("very_high", [])
        assert result.recommendation == "AVOID"

    def test_leading_whitespace(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("  LOW", [])
        assert result.recommendation == "SAFE"

    def test_trailing_whitespace(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("HIGH  ", [])
        assert result.recommendation == "HIGH RISK"

    def test_mixed_case_with_whitespace(
        self, service: RecommendationService,
    ) -> None:
        result = service.generate_recommendation("  vErY_hIgH  ", [])
        assert result.recommendation == "AVOID"


# ===========================================================================
# SECTION 3 — Unknown Risk-Level Fallback
# ===========================================================================


class TestUnknownRiskLevelFallback:
    """Unknown risk levels must fall back to USE WITH CAUTION without crashing."""

    def test_unknown_value(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("UNKNOWN", [])
        assert result.recommendation == "USE WITH CAUTION"

    def test_empty_string(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("", [])
        assert result.recommendation == "USE WITH CAUTION"

    def test_numeric_string(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("5", [])
        assert result.recommendation == "USE WITH CAUTION"

    def test_random_text(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("INVALID_LEVEL", [])
        assert result.recommendation == "USE WITH CAUTION"


# ===========================================================================
# SECTION 4 — Empty / Missing Profile Handling
# ===========================================================================


class TestEmptyProfileHandling:
    """The engine must never crash on empty or incomplete profiles."""

    def test_empty_profile_list(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("LOW", [])
        assert result.warnings == []
        assert result.recommendation == "SAFE"

    def test_profile_with_all_none_fields(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Example",
                "risk_level": "HIGH",
                "pregnancy_risk": None,
                "acne_risk": None,
                "sensitive_skin_risk": None,
                "allergy_risk": None,
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        assert result.warnings == []
        assert result.recommendation == "USE WITH CAUTION"

    def test_profile_missing_optional_keys_entirely(
        self, service: RecommendationService,
    ) -> None:
        profiles = [{"inci_name": "Example"}]
        result = service.generate_recommendation("LOW", profiles)
        assert result.warnings == []

    def test_profile_with_empty_dict(self, service: RecommendationService) -> None:
        result = service.generate_recommendation("HIGH", [{}])
        assert result.warnings == []

    def test_profile_missing_risk_level(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "pregnancy_risk": "Avoid during pregnancy",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        assert len(result.warnings) == 1
        assert result.warnings[0].type == "PREGNANCY"
        assert result.warnings[0].severity == "MODERATE"


# ===========================================================================
# SECTION 5 — Warning Generation by Type
# ===========================================================================


class TestPregnancyWarnings:
    """Pregnancy warning generation from pregnancy_risk field."""

    def test_avoid_triggers_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 1
        assert pregnancy_warnings[0].ingredient_name == "Retinol"

    def test_safe_value_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "pregnancy_risk": "Generally recognized as safe during pregnancy",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 0

    def test_contraindicated_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Salicylic Acid",
                "risk_level": "MODERATE",
                "pregnancy_risk": "Contraindicated during pregnancy",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 1

    def test_not_recommended_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Not recommended during pregnancy",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 1


class TestAcneWarnings:
    """Acne warning generation from acne_risk field."""

    def test_comedogenic_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Coconut Oil",
                "risk_level": "MODERATE",
                "acne_risk": "Comedogenic — may clog pores",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 1
        assert acne_warnings[0].ingredient_name == "Coconut Oil"

    def test_non_comedogenic_no_warning(self, service: RecommendationService) -> None:
        """Critical: 'Non-comedogenic' must NOT trigger an acne warning."""
        profiles = [
            {
                "inci_name": "Niacinamide",
                "risk_level": "LOW",
                "acne_risk": "Non-comedogenic",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 0

    def test_non_comedogenic_lowercase_no_warning(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Niacinamide",
                "risk_level": "LOW",
                "acne_risk": "non-comedogenic",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 0

    def test_may_cause_acne_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Lauric Acid",
                "risk_level": "MODERATE",
                "acne_risk": "May cause acne in some individuals",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 1

    def test_pore_clogging_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Isopropyl Myristate",
                "risk_level": "HIGH",
                "acne_risk": "Pore-clogging ingredient",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 1

    def test_acne_prone_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Cocoa Butter",
                "risk_level": "MODERATE",
                "acne_risk": "May be acne-prone for oily skin types",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 1

    def test_non_comedogenic_with_pore_clogging_still_safe(
        self, service: RecommendationService,
    ) -> None:
        """'Non-comedogenic, does not cause pore clogging' → no warning."""
        profiles = [
            {
                "inci_name": "Hyaluronic Acid",
                "risk_level": "LOW",
                "acne_risk": "Non-comedogenic, does not cause pore clogging",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        acne_warnings = [w for w in result.warnings if w.type == "ACNE"]
        assert len(acne_warnings) == 0


class TestSensitiveSkinWarnings:
    """Sensitive skin warning generation from sensitive_skin_risk field."""

    def test_irritation_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Glycolic Acid",
                "risk_level": "HIGH",
                "sensitive_skin_risk": "May cause irritation on sensitive skin",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        skin_warnings = [w for w in result.warnings if w.type == "SENSITIVE_SKIN"]
        assert len(skin_warnings) == 1

    def test_no_irritation_no_warning(self, service: RecommendationService) -> None:
        """'No irritation reported' must NOT trigger a sensitive skin warning."""
        profiles = [
            {
                "inci_name": "Panthenol",
                "risk_level": "LOW",
                "sensitive_skin_risk": "No irritation reported",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        skin_warnings = [w for w in result.warnings if w.type == "SENSITIVE_SKIN"]
        assert len(skin_warnings) == 0

    def test_not_irritating_no_warning(self, service: RecommendationService) -> None:
        """'Not irritating' must NOT trigger a sensitive skin warning."""
        profiles = [
            {
                "inci_name": "Allantoin",
                "risk_level": "LOW",
                "sensitive_skin_risk": "Not irritating for most skin types",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        skin_warnings = [w for w in result.warnings if w.type == "SENSITIVE_SKIN"]
        assert len(skin_warnings) == 0

    def test_not_suitable_triggers(self, service: RecommendationService) -> None:
        """'Not suitable for sensitive skin' IS a concern (phrase is inherently negative)."""
        profiles = [
            {
                "inci_name": "Menthol",
                "risk_level": "MODERATE",
                "sensitive_skin_risk": "Not suitable for sensitive skin",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        skin_warnings = [w for w in result.warnings if w.type == "SENSITIVE_SKIN"]
        assert len(skin_warnings) == 1

    def test_without_irritation_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "sensitive_skin_risk": "Safe without irritation",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        skin_warnings = [w for w in result.warnings if w.type == "SENSITIVE_SKIN"]
        assert len(skin_warnings) == 0


class TestAllergyWarnings:
    """Allergy warning generation from allergy_risk field."""

    def test_allergic_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Lanolin",
                "risk_level": "MODERATE",
                "allergy_risk": "May cause allergic reactions in sensitive individuals",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        allergy_warnings = [w for w in result.warnings if w.type == "ALLERGY"]
        assert len(allergy_warnings) == 1

    def test_not_allergic_no_warning(self, service: RecommendationService) -> None:
        """'Not allergic, no sensitization' must NOT trigger an allergy warning."""
        profiles = [
            {
                "inci_name": "Aloe Vera",
                "risk_level": "LOW",
                "allergy_risk": "Not allergic, no sensitization",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        allergy_warnings = [w for w in result.warnings if w.type == "ALLERGY"]
        assert len(allergy_warnings) == 0

    def test_no_allergy_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Vitamin E",
                "risk_level": "LOW",
                "allergy_risk": "No allergy reports in literature",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        allergy_warnings = [w for w in result.warnings if w.type == "ALLERGY"]
        assert len(allergy_warnings) == 0

    def test_hypersensitivity_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Nickel",
                "risk_level": "VERY_HIGH",
                "allergy_risk": "Known hypersensitivity risk",
            }
        ]
        result = service.generate_recommendation("VERY_HIGH", profiles)
        allergy_warnings = [w for w in result.warnings if w.type == "ALLERGY"]
        assert len(allergy_warnings) == 1

    def test_contact_dermatitis_triggers(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Formaldehyde",
                "risk_level": "VERY_HIGH",
                "allergy_risk": "May cause contact dermatitis",
            }
        ]
        result = service.generate_recommendation("VERY_HIGH", profiles)
        allergy_warnings = [w for w in result.warnings if w.type == "ALLERGY"]
        assert len(allergy_warnings) == 1


# ===========================================================================
# SECTION 6 — Negation-Aware Matching (False-Positive Prevention)
# ===========================================================================


class TestNegationAwareMatching:
    """Ensure negated values do not trigger false-positive warnings."""

    def test_non_comedogenic_no_acne_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Caprylic/Capric Triglyceride",
                "risk_level": "LOW",
                "acne_risk": "Non-comedogenic",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ACNE" for w in result.warnings)

    def test_non_comedogenic_hyphenated_lowercase(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Squalane",
                "risk_level": "LOW",
                "acne_risk": "non-comedogenic, lightweight",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ACNE" for w in result.warnings)

    def test_non_comedogenic_space_separated(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Squalane",
                "risk_level": "LOW",
                "acne_risk": "non comedogenic",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ACNE" for w in result.warnings)

    def test_comedogenic_still_triggers(self, service: RecommendationService) -> None:
        """Bare 'comedogenic' without negation MUST still trigger."""
        profiles = [
            {
                "inci_name": "Coconut Oil",
                "risk_level": "MODERATE",
                "acne_risk": "Comedogenic",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        assert any(w.type == "ACNE" for w in result.warnings)

    def test_no_irritation_no_skin_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Oat Extract",
                "risk_level": "LOW",
                "sensitive_skin_risk": "No irritation in clinical studies",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "SENSITIVE_SKIN" for w in result.warnings)

    def test_does_not_cause_irritation_no_warning(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Panthenol",
                "risk_level": "LOW",
                "sensitive_skin_risk": "Does not cause irritation",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "SENSITIVE_SKIN" for w in result.warnings)

    def test_will_not_cause_allergy_no_warning(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "allergy_risk": "Will not cause allergic reactions",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ALLERGY" for w in result.warnings)

    def test_without_allergy_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "allergy_risk": "Safe without allergy concerns",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ALLERGY" for w in result.warnings)

    def test_is_not_allergic_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Vitamin C",
                "risk_level": "LOW",
                "allergy_risk": "Is not allergic — well tolerated",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ALLERGY" for w in result.warnings)

    def test_doesn_t_cause_acne_no_warning(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Niacinamide",
                "risk_level": "LOW",
                "acne_risk": "Doesn't cause acne",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert not any(w.type == "ACNE" for w in result.warnings)


# ===========================================================================
# SECTION 7 — Warning Deduplication
# ===========================================================================


class TestWarningDeduplication:
    """Duplicate (warning_type, ingredient) pairs must be suppressed."""

    def test_duplicate_profile_entries(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
            },
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
            },
        ]
        result = service.generate_recommendation("HIGH", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 1

    def test_different_ingredients_same_type_not_deduplicated(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
            },
            {
                "inci_name": "Salicylic Acid",
                "risk_level": "MODERATE",
                "pregnancy_risk": "Not recommended during pregnancy",
            },
        ]
        result = service.generate_recommendation("HIGH", profiles)
        pregnancy_warnings = [w for w in result.warnings if w.type == "PREGNANCY"]
        assert len(pregnancy_warnings) == 2
        names = {w.ingredient_name for w in pregnancy_warnings}
        assert names == {"Retinol", "Salicylic Acid"}

    def test_same_ingredient_different_types_not_deduplicated(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
                "acne_risk": "May worsen acne",
            },
        ]
        result = service.generate_recommendation("HIGH", profiles)
        assert len(result.warnings) == 2
        types = {w.type for w in result.warnings}
        assert types == {"PREGNANCY", "ACNE"}


# ===========================================================================
# SECTION 8 — Warning Severity Derivation
# ===========================================================================


class TestSeverityDerivation:
    """Severity must be derived from the ingredient's risk_level."""

    def test_severity_from_low_risk(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "allergy_risk": "Rare allergic reaction",
            }
        ]
        result = service.generate_recommendation("LOW", profiles)
        assert result.warnings[0].severity == "LOW"

    def test_severity_from_moderate_risk(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Salicylic Acid",
                "risk_level": "MODERATE",
                "pregnancy_risk": "Not recommended",
            }
        ]
        result = service.generate_recommendation("MODERATE", profiles)
        assert result.warnings[0].severity == "MODERATE"

    def test_severity_from_high_risk(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        assert result.warnings[0].severity == "HIGH"

    def test_severity_from_very_high_risk(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Mercury",
                "risk_level": "VERY_HIGH",
                "allergy_risk": "Allergic reactions",
            }
        ]
        result = service.generate_recommendation("VERY_HIGH", profiles)
        assert result.warnings[0].severity == "VERY_HIGH"

    def test_severity_defaults_to_moderate_when_missing(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Unknown Ingredient",
                "pregnancy_risk": "Avoid",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        assert result.warnings[0].severity == "MODERATE"

    def test_severity_defaults_to_moderate_when_unknown(
        self, service: RecommendationService,
    ) -> None:
        profiles = [
            {
                "inci_name": "Unknown Ingredient",
                "risk_level": "INVALID",
                "pregnancy_risk": "Avoid",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        assert result.warnings[0].severity == "MODERATE"


# ===========================================================================
# SECTION 9 — Deterministic Output
# ===========================================================================


class TestDeterministicOutput:
    """Output must be identical across multiple calls with the same input."""

    def test_same_input_same_output(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid during pregnancy",
                "acne_risk": "May worsen acne",
                "sensitive_skin_risk": "May cause irritation",
                "allergy_risk": "Rare allergic reactions",
            },
            {
                "inci_name": "Glycerin",
                "risk_level": "LOW",
                "pregnancy_risk": "Safe during pregnancy",
                "acne_risk": "Non-comedogenic",
                "sensitive_skin_risk": "Gentle on skin",
                "allergy_risk": "No known allergies",
            },
        ]

        results = [
            service.generate_recommendation("MODERATE", profiles)
            for _ in range(10)
        ]

        first = results[0]
        for r in results[1:]:
            assert r.recommendation == first.recommendation
            assert r.recommendation_message == first.recommendation_message
            assert len(r.warnings) == len(first.warnings)
            for rw, fw in zip(r.warnings, first.warnings):
                assert rw.type == fw.type
                assert rw.severity == fw.severity
                assert rw.ingredient_name == fw.ingredient_name

    def test_warning_ordering_is_stable(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Z",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid",
            },
            {
                "inci_name": "A",
                "risk_level": "MODERATE",
                "pregnancy_risk": "Not recommended",
            },
        ]
        first = service.generate_recommendation("HIGH", profiles)
        second = service.generate_recommendation("HIGH", profiles)
        first_order = [w.ingredient_name for w in first.warnings]
        second_order = [w.ingredient_name for w in second.warnings]
        assert first_order == second_order


# ===========================================================================
# SECTION 10 — Multiple Warnings Across Types
# ===========================================================================


class TestMultipleWarningTypes:
    """Verify correct behavior when multiple warning types fire."""

    def test_all_four_warning_types(self, service: RecommendationService) -> None:
        profiles = [
            {
                "inci_name": "Toxic Ingredient",
                "risk_level": "VERY_HIGH",
                "pregnancy_risk": "Contraindicated",
                "acne_risk": "Comedogenic",
                "sensitive_skin_risk": "Causes irritation",
                "allergy_risk": "May cause allergic reactions",
            }
        ]
        result = service.generate_recommendation("VERY_HIGH", profiles)
        types = {w.type for w in result.warnings}
        assert types == {"PREGNANCY", "ACNE", "SENSITIVE_SKIN", "ALLERGY"}
        assert len(result.warnings) == 4

    def test_mixed_negated_and_triggered(self, service: RecommendationService) -> None:
        """One field negated, another triggered for same ingredient."""
        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "acne_risk": "Non-comedogenic",
                "pregnancy_risk": "Avoid during pregnancy",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        types = {w.type for w in result.warnings}
        assert "PREGNANCY" in types
        assert "ACNE" not in types


# ===========================================================================
# SECTION 11 — Integration with ScanRecommendation schema
# ===========================================================================


class TestSchemaIntegration:
    """Verify the output conforms to the ScanRecommendation Pydantic model."""

    def test_output_is_valid_pydantic(self, service: RecommendationService) -> None:
        from app.schemas.scan import ScanRecommendation

        result = service.generate_recommendation("LOW", [])
        assert isinstance(result, ScanRecommendation)
        result_dict = result.model_dump()
        assert "recommendation" in result_dict
        assert "recommendation_message" in result_dict
        assert "warnings" in result_dict
        assert isinstance(result_dict["warnings"], list)

    def test_warnings_are_valid_pydantic(self, service: RecommendationService) -> None:
        from app.schemas.scan import RecommendationWarning

        profiles = [
            {
                "inci_name": "Retinol",
                "risk_level": "HIGH",
                "pregnancy_risk": "Avoid",
            }
        ]
        result = service.generate_recommendation("HIGH", profiles)
        for warning in result.warnings:
            assert isinstance(warning, RecommendationWarning)
