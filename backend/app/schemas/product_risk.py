"""
Pydantic response schemas for the Product Risk Scoring Engine.

These schemas define the structured output returned by
:class:`~app.services.risk_engine.ProductRiskEngine`.  They are
intentionally decoupled from the internal scoring algorithm so that
the API layer receives a clean, stable contract regardless of how
the engine evolves.

Schema hierarchy::

    ProductRiskResult
    ├── IngredientRiskScore          (per known ingredient)
    └── UnknownIngredientRisk        (per unknown ingredient)
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Per-ingredient risk score (known ingredients)
# ---------------------------------------------------------------------------


class IngredientRiskScore(BaseModel):
    """Risk assessment for a single ingredient that was found in the
    knowledge base.

    Carries the ingredient's identity, its raw database fields
    (``safety_rating``, ``evidence_level``, ``safety_profile_risk``),
    and the composite ``score`` produced by the risk engine.
    """

    inci_name: str = Field(
        ...,
        description="Official INCI name of the ingredient",
        examples=["Niacinamide"],
    )
    common_name: Optional[str] = Field(
        default=None,
        description="Common or trade name, if available",
        examples=["Vitamin B3"],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description="Raw safety rating from the knowledge base (0-10)",
        examples=[9.0],
    )
    risk_level: str = Field(
        ...,
        description=(
            "Risk classification derived from the ingredient's composite "
            "score. One of: LOW, MODERATE, HIGH, VERY_HIGH"
        ),
        examples=["LOW"],
    )
    evidence_level: Optional[str] = Field(
        default=None,
        description="Evidence level backing the safety data",
        examples=["HIGH"],
    )
    safety_profile_risk: Optional[str] = Field(
        default=None,
        description=(
            "Risk level from the ingredient's SafetyProfile, if present"
        ),
        examples=["LOW"],
    )
    score: float = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Composite risk score computed by the engine from "
            "safety_rating, SafetyProfile risk_level, and EvidenceLevel"
        ),
        examples=[8.75],
    )


# ---------------------------------------------------------------------------
# Per-ingredient risk data (unknown ingredients)
# ---------------------------------------------------------------------------


class UnknownIngredientRisk(BaseModel):
    """Record for an ingredient that could not be found in the knowledge
    base.

    Unknown ingredients do not contribute to the overall score but
    reduce the confidence of the analysis.
    """

    name: str = Field(
        ...,
        description="Original ingredient name as submitted",
        examples=["Fragrance"],
    )
    reason: str = Field(
        ...,
        description="Why this ingredient could not be scored",
        examples=["Ingredient not found in the knowledge base."],
    )


# ---------------------------------------------------------------------------
# Top-level product risk result
# ---------------------------------------------------------------------------


class ProductRiskResult(BaseModel):
    """Complete output of the Product Risk Scoring Engine.

    Provides the overall product safety assessment alongside
    per-ingredient breakdowns for both known and unknown ingredients.
    """

    overall_score: float = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Aggregate safety score computed from all known ingredient "
            "composite scores (0-10). Higher values indicate greater "
            "safety. Unknown ingredients are excluded from this score."
        ),
        examples=[8.45],
    )
    overall_risk_level: str = Field(
        ...,
        description=(
            "Risk classification derived from the overall score. "
            "One of: LOW (>= 8.5), MODERATE (>= 6.5), HIGH (>= 4.5), "
            "VERY_HIGH (< 4.5)"
        ),
        examples=["LOW"],
    )
    confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Confidence score (0-100) reflecting analysis reliability. "
            "Reduced by unknown ingredients and weak evidence levels"
        ),
        examples=[82],
    )
    known_count: int = Field(
        ...,
        ge=0,
        description="Number of ingredients successfully scored",
        examples=[28],
    )
    unknown_count: int = Field(
        ...,
        ge=0,
        description="Number of ingredients not found in the knowledge base",
        examples=[2],
    )
    ingredient_scores: list[IngredientRiskScore] = Field(
        default_factory=list,
        description="Per-ingredient risk assessments for all known ingredients",
    )
    unknown_ingredients: list[UnknownIngredientRisk] = Field(
        default_factory=list,
        description="Records for ingredients that could not be scored",
    )
