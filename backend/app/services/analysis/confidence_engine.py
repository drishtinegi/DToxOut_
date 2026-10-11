"""
Confidence engine for the AI Ingredient Intelligence Engine.

Estimates how reliable the overall analysis is based on the quality
and completeness of the available ingredient data.  Future iterations
will incorporate AI-based reliability models; the current
implementation provides a deterministic, rule-based baseline.

Confidence rules::

    Start at 100.
    -10  for every ingredient whose ``description`` is empty.
    -10  for every ingredient whose ``safetyRating`` is below 5.
    -5   if ``commonName`` is missing (``None`` or empty).

    Clamped to the range [40, 100].
"""

from __future__ import annotations

from prisma.models import Ingredient as PrismaIngredient


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

_MIN_CONFIDENCE: int = 40
_MAX_CONFIDENCE: int = 100


class ConfidenceEngine:
    """Stateless engine that estimates analysis confidence.

    The confidence score reflects how much of the ingredient knowledge
    base was actually available during the analysis.  A score of 100
    means every ingredient had full metadata; lower scores indicate
    gaps that may reduce the reliability of the result.

    Example::

        engine = ConfidenceEngine()
        score = engine.calculate_confidence(ingredients=resolved_list)
    """

    @staticmethod
    def calculate_confidence(
        ingredients: list[PrismaIngredient],
    ) -> int:
        """Compute a confidence score for the analysis.

        Iterates over the resolved :class:`PrismaIngredient` records
        and applies deterministic deductions based on data quality.

        Deductions:

        * ``-10`` if ``ingredient.description`` is empty or whitespace.
        * ``-10`` if ``ingredient.safetyRating < 5``.
        * ``-5``  if ``ingredient.commonName`` is ``None`` or empty.

        The raw score is clamped to the range
        [:data:`_MIN_CONFIDENCE`, :data:`_MAX_CONFIDENCE`].

        Args:
            ingredients: List of resolved Prisma :class:`Ingredient`
                records that were successfully looked up in the
                knowledge base.

        Returns:
            An integer confidence score between 40 and 100 (inclusive).
        """
        if not ingredients:
            return _MIN_CONFIDENCE

        score = _MAX_CONFIDENCE

        for ingredient in ingredients:
            if not ingredient.description or not ingredient.description.strip():
                score -= 10

            if ingredient.safetyRating < 5:
                score -= 10

            if not ingredient.commonName or not ingredient.commonName.strip():
                score -= 5

        return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, score))
