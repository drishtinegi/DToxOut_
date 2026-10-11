"""
Recommendation Engine service.

Converts the numerical and categorical risk analysis produced by the
Risk Engine into meaningful, user-facing recommendations and structured
warnings.

This service is **stateless** — it does not access the database or call
any external APIs.  All input data is provided by the caller, making
the engine fully deterministic and independently testable.

The Recommendation Engine does NOT:

* Diagnose medical conditions.
* Claim that a product is medically safe.
* Guarantee safety for every individual.
* Replace a doctor or dermatologist.
* Make unsupported medical claims.

Usage::

    from app.services.recommendation_service import RecommendationService

    service = RecommendationService()
    result = service.generate_recommendation(
        overall_risk_level="LOW",
        ingredient_profiles=[...],
    )
"""

from __future__ import annotations

import logging
from typing import Optional

from app.schemas.scan import RecommendationWarning, ScanRecommendation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Recommendation mapping: risk level → label + message
# ---------------------------------------------------------------------------

_RECOMMENDATION_MAP: dict[str, tuple[str, str]] = {
    "LOW": (
        "SAFE",
        (
            "This product appears to have a low overall ingredient "
            "risk based on the available data."
        ),
    ),
    "MODERATE": (
        "USE WITH CAUTION",
        (
            "This product contains ingredients that may require "
            "caution depending on individual sensitivity and usage."
        ),
    ),
    "HIGH": (
        "HIGH RISK",
        (
            "This product contains ingredients associated with "
            "elevated risk. Review the ingredient warnings carefully."
        ),
    ),
    "VERY_HIGH": (
        "AVOID",
        (
            "This product contains one or more ingredients associated "
            "with very high risk. Avoid use unless professionally advised."
        ),
    ),
}

_DEFAULT_RECOMMENDATION: tuple[str, str] = (
    "USE WITH CAUTION",
    (
        "This product contains ingredients that may require "
        "caution depending on individual sensitivity and usage."
    ),
)


# ---------------------------------------------------------------------------
# Warning keyword detection — normalized, case-insensitive phrases
# ---------------------------------------------------------------------------
# Each mapping associates a warning type with:
#   - keyword phrases that trigger the warning (any match = concern)
#   - a severity level derived from the strength of the match
#   - a title and message template

_PREGNANCY_CONCERN_PHRASES: list[str] = [
    "avoid",
    "not recommended",
    "high risk",
    "contraindicated",
    "do not use",
    "unsafe",
    "dangerous",
    "restricted",
    "prohibited",
]

_ACNE_CONCERN_PHRASES: list[str] = [
    "comedogenic",
    "may cause acne",
    "pore-clogging",
    "pore clogging",
    "high risk",
    "acne-prone",
    "acne prone",
    "breakouts",
    "may worsen acne",
]

_SENSITIVE_SKIN_CONCERN_PHRASES: list[str] = [
    "irritation",
    "irritating",
    "may cause irritation",
    "not suitable",
    "avoid",
    "high risk",
    "sensitive skin",
    "redness",
    "inflammation",
    "may cause redness",
]

_ALLERGY_CONCERN_PHRASES: list[str] = [
    "allergic",
    "allergy",
    "hypersensitivity",
    "contact dermatitis",
    "high risk",
    "may cause allergic",
    "sensitization",
    "sensitising",
    "sensitizing",
    "hives",
    "anaphylaxis",
]


# ---------------------------------------------------------------------------
# Warning severity mapping
# ---------------------------------------------------------------------------

_SEVERITY_MAP: dict[str, str] = {
    "LOW": "LOW",
    "MODERATE": "MODERATE",
    "HIGH": "HIGH",
    "VERY_HIGH": "VERY_HIGH",
}

_DEFAULT_SEVERITY: str = "MODERATE"


# ---------------------------------------------------------------------------
# Negation detection — prevents false-positive warnings for negated values
# ---------------------------------------------------------------------------
# When a concern phrase is preceded by one of these prefixes in the
# normalized safety-profile text, the phrase is considered negated and
# does NOT trigger a warning.  For example:
#
#   "Non-comedogenic" → "comedogenic" is preceded by "non-" → no acne warning
#   "Not irritating"  → "irritating" is preceded by "not " → no skin warning
#   "No irritation"   → "irritation" is preceded by "no " → no skin warning
#
# Phrases that ARE inherently negative (e.g. "not recommended",
# "do not use", "not suitable") are never negated because the
# negation is part of the concern itself.

_NEGATION_PREFIXES: tuple[str, ...] = (
    # Direct negation — immediately before the concern phrase.
    "non-",
    "non ",
    "not ",
    "no ",
    "without ",
    # Verb-phrase negation — the negation word is separated from the
    # concern phrase by a verb such as "cause".  These are checked
    # with ``endswith`` so the verb must appear directly before the
    # phrase (e.g. "does not cause irritation").
    "does not cause ",
    "will not cause ",
    "won't cause ",
    "doesn't cause ",
    "do not cause ",
    "may not cause ",
    "did not cause ",
    "didn't cause ",
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class RecommendationService:
    """Stateless service that generates user-facing recommendations
    and structured warnings from risk analysis data.

    The service accepts the already-calculated risk-analysis result
    (overall risk level) and per-ingredient safety profile data, then
    returns a deterministic :class:`ScanRecommendation`.

    Example::

        service = RecommendationService()
        result = service.generate_recommendation(
            overall_risk_level="MODERATE",
            ingredient_profiles=[
                {
                    "inci_name": "Retinol",
                    "risk_level": "HIGH",
                    "pregnancy_risk": "Avoid during pregnancy",
                    "acne_risk": "Non-comedogenic",
                    "sensitive_skin_risk": "May cause irritation",
                    "allergy_risk": "Rarely causes allergic reactions",
                },
            ],
        )
    """

    def generate_recommendation(
        self,
        overall_risk_level: str,
        ingredient_profiles: list[dict[str, Optional[str]]],
    ) -> ScanRecommendation:
        """Generate a complete recommendation from risk analysis output.

        Combines the overall risk-level mapping with per-ingredient
        warning extraction to produce a fully populated
        :class:`ScanRecommendation`.

        Args:
            overall_risk_level: Risk classification string from the
                Risk Engine (LOW, MODERATE, HIGH, or VERY_HIGH).
            ingredient_profiles: List of dicts, each containing the
                ingredient's INCI name and its safety profile fields.
                Expected keys: ``inci_name``, ``risk_level``,
                ``pregnancy_risk``, ``acne_risk``,
                ``sensitive_skin_risk``, ``allergy_risk``.
                Values may be ``None`` when no safety profile exists.

        Returns:
            A :class:`ScanRecommendation` with recommendation label,
            message, and any extracted warnings.
        """
        recommendation, message = self._map_risk_to_recommendation(
            overall_risk_level
        )

        warnings = self._extract_warnings(ingredient_profiles)

        logger.info(
            "recommendation risk=%s rec=%s warnings=%d",
            overall_risk_level,
            recommendation,
            len(warnings),
        )

        return ScanRecommendation(
            recommendation=recommendation,
            recommendation_message=message,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Risk-level to recommendation mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_risk_to_recommendation(
        overall_risk_level: str,
    ) -> tuple[str, str]:
        """Map an overall risk level to a recommendation label and message.

        The mapping is deterministic and does not depend on any external
        data.  Unknown risk levels fall back to the default
        recommendation.

        Args:
            overall_risk_level: Risk classification string.

        Returns:
            A tuple of (recommendation_label, recommendation_message).
        """
        normalized = overall_risk_level.strip().upper()
        return _RECOMMENDATION_MAP.get(normalized, _DEFAULT_RECOMMENDATION)

    # ------------------------------------------------------------------
    # Warning extraction
    # ------------------------------------------------------------------

    def _extract_warnings(
        self,
        ingredient_profiles: list[dict[str, Optional[str]]],
    ) -> list[RecommendationWarning]:
        """Extract structured warnings from ingredient safety profiles.

        Inspects each ingredient's safety profile fields for concerning
        phrases and generates the appropriate warning.  Duplicate
        warnings for the same (type, ingredient) pair are suppressed.

        Args:
            ingredient_profiles: List of ingredient profile dicts.

        Returns:
            An ordered list of :class:`RecommendationWarning` objects.
        """
        warnings: list[RecommendationWarning] = []
        seen: set[tuple[str, str]] = set()

        for profile in ingredient_profiles:
            inci_name: str = profile.get("inci_name", "Unknown")
            risk_level: Optional[str] = profile.get("risk_level")

            for check in self._get_warning_checks():
                warning_type, phrases, title, message_template, profile_field = check
                field_value = profile.get(profile_field)

                if field_value is None:
                    continue

                if self._value_indicates_concern(field_value, phrases):
                    dedup_key = (warning_type, inci_name)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    severity = self._derive_severity(risk_level)
                    warnings.append(
                        RecommendationWarning(
                            type=warning_type,
                            severity=severity,
                            title=title,
                            message=message_template,
                            ingredient_name=inci_name,
                        )
                    )

        return warnings

    def _get_warning_checks(
        self,
    ) -> list[tuple[str, list[str], str, str, str]]:
        """Return the list of warning type configurations.

        Each entry is a tuple of:
            (warning_type, concern_phrases, title, message, profile_field)

        Returns:
            List of warning type configuration tuples.
        """
        return [
            (
                "PREGNANCY",
                _PREGNANCY_CONCERN_PHRASES,
                "Pregnancy Warning",
                "One or more ingredients may not be suitable during pregnancy.",
                "pregnancy_risk",
            ),
            (
                "ACNE",
                _ACNE_CONCERN_PHRASES,
                "Acne Warning",
                "One or more ingredients may be associated with acne or comedogenicity.",
                "acne_risk",
            ),
            (
                "SENSITIVE_SKIN",
                _SENSITIVE_SKIN_CONCERN_PHRASES,
                "Sensitive Skin Warning",
                "One or more ingredients may cause irritation on sensitive skin.",
                "sensitive_skin_risk",
            ),
            (
                "ALLERGY",
                _ALLERGY_CONCERN_PHRASES,
                "Allergy Warning",
                "One or more ingredients may cause allergic reactions in some individuals.",
                "allergy_risk",
            ),
        ]

    # ------------------------------------------------------------------
    # Phrase matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_value(value: str) -> str:
        """Normalize a free-text value for consistent matching.

        Strips whitespace, lowercases, and collapses multiple spaces.

        Args:
            value: Raw string value from the safety profile.

        Returns:
            Normalized lowercase string.
        """
        return " ".join(value.strip().lower().split())

    @staticmethod
    def _value_indicates_concern(
        value: str,
        concern_phrases: list[str],
    ) -> bool:
        """Check if a safety profile value contains any concern phrases.

        Performs case-insensitive substring matching against the provided
        list of concern phrases, with negation awareness.  A phrase that
        is preceded by a common negation prefix (e.g. "non-", "not ",
        "no ") is treated as safe and does not trigger a warning.

        Examples of negation handling::

            "Non-comedogenic"  → "comedogenic" negated → no concern
            "Not irritating"   → "irritating" negated  → no concern
            "No irritation"    → "irritation" negated  → no concern
            "Comedogenic"      → no negation            → concern ✓
            "May cause acne"   → no negation            → concern ✓

        Args:
            value: Free-text value from a safety profile field.
            concern_phrases: List of normalized phrases that indicate
                a safety concern.

        Returns:
            ``True`` if any concern phrase is found in the value and
            is not negated.
        """
        normalized = RecommendationService._normalize_value(value)
        for phrase in concern_phrases:
            if phrase not in normalized:
                continue
            if RecommendationService._is_negated(normalized, phrase):
                continue
            return True
        return False

    @staticmethod
    def _is_negated(normalized_value: str, phrase: str) -> bool:
        """Detect whether a matched phrase is preceded by a negation prefix.

        Checks if the text immediately before the phrase match ends with
        a common negation pattern such as ``"non-"``, ``"not "``, or
        ``"no "``.  This prevents false-positive warnings for values
        like ``"Non-comedogenic"`` or ``"No irritation"``.

        Args:
            normalized_value: The fully normalized (lowercased,
                whitespace-collapsed) safety profile value.
            phrase: The concern phrase that was found as a substring.

        Returns:
            ``True`` if the phrase is negated, ``False`` otherwise.
        """
        idx = normalized_value.find(phrase)
        if idx <= 0:
            return False
        preceding = normalized_value[:idx]
        return any(preceding.endswith(neg) for neg in _NEGATION_PREFIXES)

    # ------------------------------------------------------------------
    # Severity derivation
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_severity(risk_level: Optional[str]) -> str:
        """Derive a warning severity from an ingredient's risk level.

        Maps the ingredient's ``risk_level`` from its safety profile
        to a severity string.  Falls back to MODERATE when the risk
        level is missing or unrecognized.

        Args:
            risk_level: Risk level string from the ingredient's
                SafetyProfile, or ``None``.

        Returns:
            Severity string: LOW, MODERATE, HIGH, or VERY_HIGH.
        """
        if risk_level is None:
            return _DEFAULT_SEVERITY

        normalized = risk_level.strip().upper()
        return _SEVERITY_MAP.get(normalized, _DEFAULT_SEVERITY)
