"""
Explanation engine for the AI Ingredient Intelligence Engine.

Generates natural-language summaries and structured reason lists
for individual ingredients and the overall product.  Future
iterations will use AI models to produce nuanced, context-aware
explanations; the current implementation provides deterministic
rule-based text that conforms to the public interface.

All methods are stateless pure functions.  The engine does not
perform database lookups or HTTP requests.
"""

from __future__ import annotations

from typing import Any

from app.schemas.analysis import (
    IngredientExplanation,
    ProductExplanation,
)
from app.services.risk_engine import ProductRiskEngine


class ExplanationEngine:
    """Stateless engine that produces human-readable explanations.

    Each method returns text or structured data that is ready for
    direct inclusion in API responses.  Deterministic implementations
    produce grammatically correct, informative content so that
    downstream consumers can be developed and tested independently
    of the AI backend.

    Example::

        engine = ExplanationEngine()
        text = engine.generate_summary("LOW")
        reasons = engine.generate_reasons(9.0, "LOW", 30)
    """

    def __init__(self) -> None:
        self._risk_engine = ProductRiskEngine()

    # ------------------------------------------------------------------
    # Product-level summary
    # ------------------------------------------------------------------

    @staticmethod
    def generate_summary(overall_risk: str) -> str:
        """Return a product-level summary based on the overall risk classification.

        The summary is a single sentence intended for consumer-facing
        display.  Each risk level maps to a fixed, professionally
        worded statement.

        Args:
            overall_risk: Classified overall risk level produced by
                the :class:`RiskEngine`.  Must be one of ``"LOW"``,
                ``"MODERATE"``, ``"HIGH"``, or ``"VERY_HIGH"``.

        Returns:
            A non-empty summary string.

        Example::

            >>> ExplanationEngine.generate_summary("MODERATE")
            'This product contains a mixture of generally safe and moderate-risk ingredients.'
        """
        _SUMMARIES: dict[str, str] = {
            "LOW": (
                "This product appears to contain mostly low-risk "
                "cosmetic ingredients."
            ),
            "MODERATE": (
                "This product contains a mixture of generally safe "
                "and moderate-risk ingredients."
            ),
            "HIGH": (
                "This product contains several ingredients that may "
                "require caution."
            ),
            "VERY_HIGH": (
                "This product contains multiple high-risk ingredients "
                "and should be reviewed carefully."
            ),
        }
        return _SUMMARIES.get(
            overall_risk,
            "Unable to determine product safety.",
        )

    # ------------------------------------------------------------------
    # Product-level reasons
    # ------------------------------------------------------------------

    @staticmethod
    def generate_reasons(
        overall_score: float,
        overall_risk: str,
        ingredient_count: int,
    ) -> list[str]:
        """Generate a list of deterministic product-level reasons.

        Reasons are factual statements derived from the scoring
        thresholds, risk classification, and ingredient count.
        They are ordered from most to least impactful.

        Deterministic rules:

        * Score >= 8.5 — ``"The overall ingredient safety rating is excellent."``
        * Score >= 6.5 and < 8.5 — ``"The overall ingredient safety rating is good."``
        * Score >= 4.5 and < 6.5 — ``"The overall ingredient safety rating is moderate."``
        * Score < 4.5 — ``"The overall ingredient safety rating is concerning."``
        * Risk is HIGH or VERY_HIGH — ``"Some ingredients have moderate safety ratings."``
        * Ingredient count > 15 — ``"This product contains a large number of ingredients."``
        * Ingredient count < 5 — ``"This product has a relatively simple formulation."``

        Args:
            overall_score: Aggregate safety score (0.0 – 10.0).
            overall_risk: Classified overall risk level.
            ingredient_count: Number of recognised ingredients.

        Returns:
            An ordered list of reason strings (may be empty).

        Example::

            >>> ExplanationEngine.generate_reasons(9.0, "LOW", 30)
            ['The overall ingredient safety rating is excellent.', ...]
        """
        reasons: list[str] = []

        if overall_score >= 8.5:
            reasons.append("The overall ingredient safety rating is excellent.")
        elif overall_score >= 6.5:
            reasons.append("The overall ingredient safety rating is good.")
        elif overall_score >= 4.5:
            reasons.append("The overall ingredient safety rating is moderate.")
        else:
            reasons.append("The overall ingredient safety rating is concerning.")

        if overall_risk in ("HIGH", "VERY_HIGH"):
            reasons.append(
                "Some ingredients have moderate safety ratings."
            )

        if ingredient_count > 15:
            reasons.append(
                "This product contains a large number of ingredients."
            )
        elif ingredient_count < 5:
            reasons.append(
                "This product has a relatively simple formulation."
            )

        return reasons

    # ------------------------------------------------------------------
    # Per-ingredient explanations
    # ------------------------------------------------------------------

    def generate_ingredient_explanations(
        self,
        ingredient_data: list[dict[str, Any]],
    ) -> list[IngredientExplanation]:
        """Create an :class:`IngredientExplanation` for every resolved ingredient.

        Each explanation includes the ingredient name, its safety
        rating, the risk level computed by the :class:`RiskEngine`,
        and a single-sentence deterministic reason.

        Reason thresholds:

        * Safety >= 8.5 — ``"This ingredient is generally considered safe."``
        * Safety >= 6.5 — ``"This ingredient is considered safe for most users."``
        * Safety >= 4.5 — ``"This ingredient may require caution for sensitive individuals."``
        * Safety <  4.5 — ``"This ingredient may present higher safety concerns."``

        Args:
            ingredient_data: List of resolved ingredient dicts as
                produced by
                :meth:`~AnalysisService._resolve_ingredients`.  Each
                dict must contain at least ``"ingredient"`` (a Prisma
                :class:`Ingredient` record) and ``"safety_rating"``
                (a float).

        Returns:
            A list of :class:`IngredientExplanation` objects in the
            same order as the input.

        Raises:
            ValueError: If *ingredient_data* is empty.

        Example::

            >>> engine = ExplanationEngine()
            >>> data = [{"ingredient": ing, "safety_rating": 9.0}]
            >>> explanations = engine.generate_ingredient_explanations(data)
        """
        if not ingredient_data:
            raise ValueError(
                "Cannot generate explanations for an empty ingredient list."
            )

        explanations: list[IngredientExplanation] = []

        for data in ingredient_data:
            ingredient = data["ingredient"]
            safety_rating: float = data["safety_rating"]
            risk_level = self._risk_engine.calculate_risk_level(safety_rating)
            reason = self._ingredient_reason(safety_rating)

            explanations.append(
                IngredientExplanation(
                    ingredient_name=ingredient.inciName,
                    safety_rating=safety_rating,
                    risk_level=risk_level,
                    reason=reason,
                )
            )

        return explanations

    # ------------------------------------------------------------------
    # Composite: build full ProductExplanation
    # ------------------------------------------------------------------

    def build_product_explanation(
        self,
        overall_score: float,
        overall_risk: str,
        ingredient_count: int,
        ingredient_data: list[dict[str, Any]],
    ) -> ProductExplanation:
        """Assemble a complete :class:`ProductExplanation`.

        Convenience method that calls :meth:`generate_summary`,
        :meth:`generate_reasons`, and
        :meth:`generate_ingredient_explanations` and returns a
        single schema object ready for inclusion in
        :class:`~app.schemas.analysis.AnalysisResult`.

        Args:
            overall_score: Aggregate safety score (0.0 – 10.0).
            overall_risk: Classified overall risk level.
            ingredient_count: Number of recognised ingredients.
            ingredient_data: Resolved ingredient dicts from the
                orchestrator.

        Returns:
            A fully populated :class:`ProductExplanation`.

        Raises:
            ValueError: If *ingredient_data* is empty.
        """
        return ProductExplanation(
            summary=self.generate_summary(overall_risk),
            reasons=self.generate_reasons(
                overall_score, overall_risk, ingredient_count,
            ),
            ingredient_explanations=self.generate_ingredient_explanations(
                ingredient_data,
            ),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ingredient_reason(safety_rating: float) -> str:
        """Return a single-sentence reason for an ingredient's safety rating.

        Args:
            safety_rating: Numeric safety rating (0.0 – 10.0).

        Returns:
            A deterministic reason string.
        """
        if safety_rating >= 8.5:
            return "This ingredient is generally considered safe."
        if safety_rating >= 6.5:
            return "This ingredient is considered safe for most users."
        if safety_rating >= 4.5:
            return (
                "This ingredient may require caution for sensitive individuals."
            )
        return "This ingredient may present higher safety concerns."
