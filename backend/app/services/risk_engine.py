"""
Product Risk Scoring Engine.

A dedicated, standalone module that computes product-level safety scores
and risk classifications by combining multiple data signals from the
DToxOut knowledge base.

Signals considered:

* ``Ingredient.safetyRating``       — primary numeric safety signal
* ``SafetyProfile.riskLevel``       — expert-judgment risk classification
* ``Ingredient.evidenceLevel``      — quality of supporting evidence

Design principles:

* **No database access** — the engine is a pure-function stateless
  class.  The caller resolves ingredients from the database and passes
  the data in.  This keeps the engine testable, reusable, and decoupled
  from the ORM.

* **Graceful unknown handling** — ingredients not found in the knowledge
  base are recorded but excluded from scoring.  They reduce the
  ``confidence`` score proportionally instead of failing the entire
  analysis.

* **Centralized constants** — all magic numbers, thresholds, and weight
  mappings live in module-level dictionaries so they can be tuned or
  extended without touching algorithmic code.

Scoring algorithm (per-ingredient)::

    base_score      = safety_rating              (0-10)
    risk_weight     = RISK_LEVEL_WEIGHTS[risk]   (1-10)
    evidence_weight = EVIDENCE_WEIGHTS[evidence] * 10  (0-10)

    composite = (base_score × 0.60) + (risk_weight × 0.25) + (evidence_weight × 0.15)

Overall score::

    overall = mean(composite_scores of all known ingredients)

Risk-level mapping::

    >= 8.5  ->  LOW
    >= 6.5  ->  MODERATE
    >= 4.5  ->  HIGH
    <  4.5  ->  VERY_HIGH

Confidence calculation::

    unknown_ratio   = unknown_count / total_count
    unknown_penalty = unknown_ratio × 40          (max 40 points)

    avg_evidence    = mean(evidence_weight for known ingredients)
    evidence_penalty = (1 - avg_evidence) × 30    (max 30 points)

    confidence      = clamp(100 - unknown_penalty - evidence_penalty, 0, 100)

Usage::

    from app.services.risk_engine import ProductRiskEngine

    engine = ProductRiskEngine()
    result = engine.analyze(
        resolved_ingredients=[...],
        unknown_names=["Fragrance"],
    )
"""

from __future__ import annotations

import logging
from typing import Optional

from app.schemas.product_risk import (
    IngredientRiskScore,
    ProductRiskResult,
    UnknownIngredientRisk,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Centralized constants — RiskLevel to numeric weight
# ---------------------------------------------------------------------------
# Maps each RiskLevel enum value to a numeric weight on the same 0–10
# scale as safety_rating.  These weights represent expert judgment about
# how risky an ingredient is, independent of the raw safety number.
#
# LOW      = 10  (safest)
# MODERATE = 7
# HIGH     = 4
# VERY_HIGH = 1 (most dangerous)

RISK_LEVEL_WEIGHTS: dict[str, float] = {
    "LOW": 10.0,
    "MODERATE": 7.0,
    "HIGH": 4.0,
    "VERY_HIGH": 1.0,
}

# ---------------------------------------------------------------------------
# Centralized constants — EvidenceLevel to confidence multiplier
# ---------------------------------------------------------------------------
# Maps each EvidenceLevel enum value to a 0.0–1.0 multiplier reflecting
# how much we trust the safety data backing an ingredient.  Higher
# evidence means the safety_rating is more reliable.
#
# VERY_HIGH = 1.0  (fully backed by strong evidence)
# HIGH      = 0.9
# MODERATE  = 0.7
# LOW       = 0.5  (weak or preliminary evidence)

EVIDENCE_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "VERY_HIGH": 1.0,
    "HIGH": 0.9,
    "MODERATE": 0.7,
    "LOW": 0.5,
}

# ---------------------------------------------------------------------------
# Centralized constants — risk-level thresholds
# ---------------------------------------------------------------------------
# Score-to-classification mapping.  Thresholds are checked from highest
# to lowest; the first matching threshold wins.

RISK_THRESHOLDS: list[tuple[float, str]] = [
    (8.5, "LOW"),
    (6.5, "MODERATE"),
    (4.5, "HIGH"),
]
DEFAULT_RISK_LEVEL: str = "VERY_HIGH"

# ---------------------------------------------------------------------------
# Centralized constants — scoring weights
# ---------------------------------------------------------------------------
# The per-ingredient composite score is a weighted average of three
# signals.  The weights must sum to 1.0.
#
# 60% safety_rating   — the primary ground-truth signal
# 25% risk_level      — expert judgment providing a secondary check
# 15% evidence_level  — adjusts for how well-backed the rating is

WEIGHT_SAFETY_RATING: float = 0.60
WEIGHT_RISK_LEVEL: float = 0.25
WEIGHT_EVIDENCE_LEVEL: float = 0.15

# ---------------------------------------------------------------------------
# Centralized constants — confidence penalties
# ---------------------------------------------------------------------------
# Maximum points deducted for unknown ingredients (40) and weak evidence
# (30).  The remaining 30 points are the implicit "base trust" that
# cannot be removed.

_UNKNOWN_PENALTY_MAX: float = 40.0
_EVIDENCE_PENALTY_MAX: float = 30.0

# Per-ingredient unknown fallback penalty when total count is zero.
_MIN_CONFIDENCE: int = 0
_MAX_CONFIDENCE: int = 100


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ProductRiskEngine:
    """Stateless engine that computes product-level risk scores.

    The engine exposes pure functions that accept pre-resolved ingredient
    data and return deterministic results.  It does not perform any
    database lookups — callers are responsible for resolving ingredient
    names to their knowledge-base records before invoking the engine.

    All public methods are designed to be independently testable and
    composable.  The top-level :meth:`analyze` method orchestrates a
    full scoring pipeline, but each helper can be used in isolation.

    Example::

        engine = ProductRiskEngine()

        # Score a single ingredient
        score = engine.score_ingredient(
            safety_rating=9.0,
            risk_level="LOW",
            evidence_level="HIGH",
        )

        # Full analysis
        result = engine.analyze(
            resolved_ingredients=[
                {
                    "inci_name": "Niacinamide",
                    "common_name": "Vitamin B3",
                    "safety_rating": 9.0,
                    "risk_level": "LOW",
                    "evidence_level": "HIGH",
                },
            ],
            unknown_names=["Fragrance"],
        )
    """

    # ------------------------------------------------------------------
    # Per-ingredient scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_ingredient(
        safety_rating: float,
        risk_level: Optional[str] = None,
        evidence_level: Optional[str] = None,
    ) -> float:
        """Compute a composite risk score for a single ingredient.

        The composite is a weighted average of three signals:

        * **safety_rating** (60%) — the raw numeric safety value from
          the knowledge base.
        * **risk_level** (25%) — the expert-judgment classification
          from the ingredient's SafetyProfile, mapped to a numeric
          weight via :data:`RISK_LEVEL_WEIGHTS`.
        * **evidence_level** (15%) — the evidence quality, mapped to a
          numeric weight via :data:`EVIDENCE_CONFIDENCE_WEIGHTS` and
          scaled to 0–10.

        When ``risk_level`` or ``evidence_level`` is ``None`` (e.g.
        the ingredient has no SafetyProfile), the missing signal is
        replaced by a neutral midpoint value (5.0 for risk_level,
        5.0 for evidence_level) so the other signals still contribute
        proportionally.

        Args:
            safety_rating: Numeric safety rating from the knowledge
                base (0.0 – 10.0).
            risk_level: Risk classification string from the
                ingredient's SafetyProfile, or ``None``.
            evidence_level: Evidence level string from the ingredient
                record, or ``None``.

        Returns:
            Composite score between 0.0 and 10.0, rounded to two
            decimal places.

        Example::

            >>> ProductRiskEngine.score_ingredient(9.0, "LOW", "HIGH")
            8.75

            >>> ProductRiskEngine.score_ingredient(9.0)
            5.4
        """
        base_score = safety_rating

        if risk_level is not None and risk_level in RISK_LEVEL_WEIGHTS:
            risk_weight = RISK_LEVEL_WEIGHTS[risk_level]
        else:
            risk_weight = 5.0

        if evidence_level is not None and evidence_level in EVIDENCE_CONFIDENCE_WEIGHTS:
            evidence_weight = EVIDENCE_CONFIDENCE_WEIGHTS[evidence_level] * 10.0
        else:
            evidence_weight = 5.0

        composite = (
            base_score * WEIGHT_SAFETY_RATING
            + risk_weight * WEIGHT_RISK_LEVEL
            + evidence_weight * WEIGHT_EVIDENCE_LEVEL
        )

        return round(composite, 2)

    # ------------------------------------------------------------------
    # Overall score
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_overall_score(ingredient_scores: list[float]) -> float:
        """Compute the aggregate safety score from per-ingredient composites.

        The overall score is the arithmetic mean of all individual
        ingredient composite scores, rounded to two decimal places.

        Every ingredient carries equal weight.  Future versions may
        introduce concentration-based or category-based weighting.

        Args:
            ingredient_scores: Composite scores produced by
                :meth:`score_ingredient` for each known ingredient.

        Returns:
            Aggregate score between 0.0 and 10.0.

        Raises:
            ValueError: If *ingredient_scores* is empty.

        Example::

            >>> ProductRiskEngine.calculate_overall_score([9.0, 8.5, 7.0])
            8.17
        """
        if not ingredient_scores:
            raise ValueError(
                "Cannot calculate overall score from an empty score list."
            )

        return round(sum(ingredient_scores) / len(ingredient_scores), 2)

    # ------------------------------------------------------------------
    # Risk-level classification
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_risk_level(score: float) -> str:
        """Classify a numeric score as a human-readable risk level.

        Deterministic thresholds:

        * **LOW**      — score >= 8.5
        * **MODERATE**  — score >= 6.5
        * **HIGH**      — score >= 4.5
        * **VERY_HIGH** — score < 4.5

        Args:
            score: Safety score on a 0.0 – 10.0 scale.

        Returns:
            One of ``"LOW"``, ``"MODERATE"``, ``"HIGH"``, or
            ``"VERY_HIGH"``.

        Example::

            >>> ProductRiskEngine.calculate_risk_level(9.0)
            'LOW'

            >>> ProductRiskEngine.calculate_risk_level(5.0)
            'HIGH'
        """
        for threshold, label in RISK_THRESHOLDS:
            if score >= threshold:
                return label
        return DEFAULT_RISK_LEVEL

    # ------------------------------------------------------------------
    # Confidence calculation
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_confidence(
        total_count: int,
        unknown_count: int,
        evidence_levels: Optional[list[str]] = None,
    ) -> int:
        """Estimate the reliability of the overall risk assessment.

        Confidence starts at 100 and is reduced by two factors:

        1. **Unknown-ingredient penalty** — each unknown ingredient
           reduces confidence proportionally.  The maximum penalty is
           40 points when *all* ingredients are unknown.

           Formula::

               unknown_ratio = unknown_count / total_count
               unknown_penalty = unknown_ratio × 40

        2. **Evidence penalty** — weak evidence across known ingredients
           reduces confidence.  The maximum penalty is 30 points when
           every known ingredient has ``LOW`` evidence.

           Formula::

               avg_evidence = mean(evidence_weight[e] for known ingredients)
               evidence_penalty = (1 - avg_evidence) × 30

        The final score is clamped to [0, 100].

        When ``total_count`` is 0 (all ingredients are unknown), the
        confidence is 0.

        Args:
            total_count: Total number of ingredients submitted for
                analysis (known + unknown).
            unknown_count: Number of ingredients not found in the
                knowledge base.
            evidence_levels: Evidence level strings for each **known**
                ingredient.  May be empty if no evidence data is
                available, in which case the evidence penalty is
                skipped.

        Returns:
            Integer confidence score between 0 and 100 (inclusive).

        Example::

            >>> ProductRiskEngine.calculate_confidence(30, 2, ["HIGH"] * 28)
            97

            >>> ProductRiskEngine.calculate_confidence(10, 10)
            0
        """
        if total_count == 0:
            return _MIN_CONFIDENCE

        known_count = total_count - unknown_count
        if known_count == 0:
            return _MIN_CONFIDENCE

        # Unknown penalty
        unknown_ratio = unknown_count / total_count
        unknown_penalty = unknown_ratio * _UNKNOWN_PENALTY_MAX

        # Evidence penalty
        evidence_penalty = 0.0
        if evidence_levels:
            weights = [
                EVIDENCE_CONFIDENCE_WEIGHTS.get(ev, 0.5)
                for ev in evidence_levels
            ]
            avg_evidence = sum(weights) / len(weights)
            evidence_penalty = (1.0 - avg_evidence) * _EVIDENCE_PENALTY_MAX

        raw = _MAX_CONFIDENCE - unknown_penalty - evidence_penalty
        return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, int(round(raw))))

    # ------------------------------------------------------------------
    # Full analysis pipeline
    # ------------------------------------------------------------------

    def analyze(
        self,
        resolved_ingredients: list[dict],
        unknown_names: Optional[list[str]] = None,
    ) -> ProductRiskResult:
        """Run the complete product risk scoring pipeline.

        Orchestrates all sub-methods to produce a fully populated
        :class:`ProductRiskResult`.  This is the primary public entry
        point for the engine.

        Execution flow:

            1. Score each known ingredient via :meth:`score_ingredient`.
            2. Compute the overall score via
               :meth:`calculate_overall_score`.
            3. Classify the overall risk via :meth:`calculate_risk_level`.
            4. Compute the confidence via :meth:`calculate_confidence`.
            5. Build per-ingredient and unknown-ingredient records.
            6. Assemble and return the :class:`ProductRiskResult`.

        Args:
            resolved_ingredients: List of dicts, each representing a
                successfully looked-up ingredient.  Required keys:

                * ``"inci_name"``   — ``str``
                * ``"common_name"`` — ``str | None``
                * ``"safety_rating"`` — ``float`` (0–10)
                * ``"risk_level"``  — ``str | None`` (from SafetyProfile)
                * ``"evidence_level"`` — ``str | None``

            unknown_names: List of ingredient name strings that could
                not be found in the knowledge base.  Defaults to an
                empty list.

        Returns:
            A fully populated :class:`ProductRiskResult`.

        Raises:
            ValueError: If *resolved_ingredients* is empty AND
                *unknown_names* is empty.

        Example::

            >>> engine = ProductRiskEngine()
            >>> result = engine.analyze(
            ...     resolved_ingredients=[
            ...         {
            ...             "inci_name": "Niacinamide",
            ...             "common_name": "Vitamin B3",
            ...             "safety_rating": 9.0,
            ...             "risk_level": "LOW",
            ...             "evidence_level": "HIGH",
            ...         },
            ...     ],
            ...     unknown_names=["Fragrance"],
            ... )
            >>> result.known_count
            1
            >>> result.unknown_count
            1
        """
        if not resolved_ingredients and not unknown_names:
            raise ValueError(
                "Cannot analyze an empty ingredient list.  Provide at "
                "least one resolved or unknown ingredient."
            )

        unknown_names = unknown_names or []

        # --- Step 1: Score each known ingredient ---
        ingredient_scores: list[IngredientRiskScore] = []
        composite_scores: list[float] = []
        evidence_levels: list[str] = []

        for data in resolved_ingredients:
            inci_name: str = data["inci_name"]
            common_name: Optional[str] = data.get("common_name")
            safety_rating: float = data["safety_rating"]
            risk_level: Optional[str] = data.get("risk_level")
            evidence_level: Optional[str] = data.get("evidence_level")

            composite = self.score_ingredient(
                safety_rating=safety_rating,
                risk_level=risk_level,
                evidence_level=evidence_level,
            )

            individual_risk = self.calculate_risk_level(composite)

            ingredient_scores.append(
                IngredientRiskScore(
                    inci_name=inci_name,
                    common_name=common_name,
                    safety_rating=safety_rating,
                    risk_level=individual_risk,
                    evidence_level=evidence_level,
                    safety_profile_risk=risk_level,
                    score=composite,
                )
            )

            composite_scores.append(composite)

            if evidence_level is not None:
                evidence_levels.append(evidence_level)

        # --- Step 2: Overall score ---
        known_count = len(composite_scores)
        unknown_count = len(unknown_names)
        total_count = known_count + unknown_count

        if known_count > 0:
            overall_score = self.calculate_overall_score(composite_scores)
        else:
            overall_score = 0.0

        # --- Step 3: Risk-level classification ---
        overall_risk_level = self.calculate_risk_level(overall_score)

        # --- Step 4: Confidence ---
        confidence = self.calculate_confidence(
            total_count=total_count,
            unknown_count=unknown_count,
            evidence_levels=evidence_levels if evidence_levels else None,
        )

        # --- Step 5: Unknown ingredient records ---
        unknown_risks = [
            UnknownIngredientRisk(
                name=name,
                reason="Ingredient not found in the knowledge base.",
            )
            for name in unknown_names
        ]

        logger.info(
            "risk_analysis known=%d unknown=%d score=%.2f risk=%s confidence=%d",
            known_count,
            unknown_count,
            overall_score,
            overall_risk_level,
            confidence,
        )

        # --- Step 6: Assemble result ---
        return ProductRiskResult(
            overall_score=overall_score,
            overall_risk_level=overall_risk_level,
            confidence=confidence,
            known_count=known_count,
            unknown_count=unknown_count,
            ingredient_scores=ingredient_scores,
            unknown_ingredients=unknown_risks,
        )
