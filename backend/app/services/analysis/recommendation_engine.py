"""
Recommendation engine for the AI Ingredient Intelligence Engine.

Generates a single deterministic :class:`ProductRecommendation`
containing skin-type suitability, precautions, and usage guidance.

Risk thresholds used for behaviour branching::

    >= 8.5  ->  LOW
    >= 6.5  ->  MODERATE
    >= 4.5  ->  HIGH
    <  4.5  ->  VERY_HIGH
"""

from __future__ import annotations

from typing import Any

from app.schemas.analysis import OverallAnalysis, ProductRecommendation


# ---------------------------------------------------------------------------
# Supported skin types
# ---------------------------------------------------------------------------

_SKIN_TYPES: list[str] = [
    "oily",
    "dry",
    "combination",
    "sensitive",
    "normal",
]


class RecommendationEngine:
    """Stateless engine that produces a product-level recommendation.

    Each method is independently callable for testing.  The top-level
    :meth:`generate_recommendations` assembles the final
    :class:`ProductRecommendation`.

    Example::

        engine = RecommendationEngine()
        rec = engine.generate_recommendations(
            ingredient_data=[...],
            overall=overall_analysis,
        )
    """

    # ------------------------------------------------------------------
    # Skin-type recommendation
    # ------------------------------------------------------------------

    @staticmethod
    def recommend_skin_types(
        ingredient_data: list[dict[str, Any]],
        overall_risk: str,
    ) -> list[str]:
        """Return skin types the product is suitable for.

        Rules:

        * LOW risk  → all five skin types.
        * MODERATE  → oily, combination, normal only.
        * HIGH      → oily only.
        * VERY_HIGH → empty list (not recommended).

        Args:
            ingredient_data: Resolved ingredient dicts (for future use
                when AI models inspect individual ingredients).
            overall_risk: Risk level string from the risk engine.

        Returns:
            A list of skin-type strings.
        """
        if overall_risk == "LOW":
            return list(_SKIN_TYPES)
        if overall_risk == "MODERATE":
            return ["oily", "combination", "normal"]
        if overall_risk == "HIGH":
            return ["oily"]
        return []

    # ------------------------------------------------------------------
    # Precautions
    # ------------------------------------------------------------------

    @staticmethod
    def recommend_precautions(
        overall_risk: str,
        ingredient_count: int,
    ) -> list[str]:
        """Return usage precautions derived from risk and ingredient count.

        Rules:

        * ALWAYS include the universal patch-test and irritation warnings.
        * HIGH / VERY_HIGH → add dermatologist-consultation warning.
        * ingredient_count > 30 → add complexity warning.
        * VERY_HIGH → add do-not-use warning.

        Args:
            overall_risk: Risk level string from the risk engine.
            ingredient_count: Number of recognised ingredients.

        Returns:
            An ordered list of precautionary strings.
        """
        precautions: list[str] = [
            "Perform a patch test before first use",
            "Discontinue use if irritation occurs",
        ]

        if overall_risk in ("HIGH", "VERY_HIGH"):
            precautions.append(
                "Consult a dermatologist if you have sensitive or compromised skin"
            )

        if ingredient_count > 30:
            precautions.append(
                "This product contains a large number of ingredients; "
                "consider patch testing on a small area first"
            )

        if overall_risk == "VERY_HIGH":
            precautions.append(
                "This product is not recommended due to high-risk ingredients"
            )

        return precautions

    # ------------------------------------------------------------------
    # Usage guidance
    # ------------------------------------------------------------------

    @staticmethod
    def recommend_usage(overall_risk: str) -> str:
        """Return a short usage-guidance string for the product.

        Rules:

        * LOW / MODERATE → standard morning-and-evening guidance.
        * HIGH           → evening-only guidance.
        * VERY_HIGH      → not-recommended notice.

        Args:
            overall_risk: Risk level string from the risk engine.

        Returns:
            A single human-readable usage-guidance sentence.
        """
        if overall_risk in ("LOW", "MODERATE"):
            return "Apply to clean skin morning and evening as part of your routine."
        if overall_risk == "HIGH":
            return (
                "Use in the evening only. Avoid morning use and always "
                "follow with sunscreen if used during the day."
            )
        return (
            "This product is not recommended for use due to its high-risk profile."
        )

    # ------------------------------------------------------------------
    # Top-level assembly
    # ------------------------------------------------------------------

    @staticmethod
    def generate_recommendations(
        ingredient_data: list[dict[str, Any]],
        overall: OverallAnalysis,
    ) -> ProductRecommendation:
        """Assemble a complete :class:`ProductRecommendation`.

        Delegates to the individual helper methods and combines their
        outputs into a single schema-ready object.

        Args:
            ingredient_data: Resolved ingredient dicts from the
                analysis service.
            overall: The :class:`OverallAnalysis` produced by the risk
                engine (with ``summary`` already populated by the
                explanation engine).

        Returns:
            A fully populated :class:`ProductRecommendation`.
        """
        recommended_for = RecommendationEngine.recommend_skin_types(
            ingredient_data=ingredient_data,
            overall_risk=overall.overall_risk,
        )
        precautions = RecommendationEngine.recommend_precautions(
            overall_risk=overall.overall_risk,
            ingredient_count=overall.ingredient_count,
        )
        usage_guidance = RecommendationEngine.recommend_usage(
            overall_risk=overall.overall_risk,
        )

        return ProductRecommendation(
            recommended_for=recommended_for,
            precautions=precautions,
            usage_guidance=usage_guidance,
        )
