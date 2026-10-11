"""
Pydantic schemas for the AI Ingredient Intelligence Engine.

AnalysisResult          -- top-level container for a full product analysis
OverallAnalysis         -- aggregate score, risk, and ingredient count
IngredientExplanation   -- per-ingredient risk, rating, and reason
ProductExplanation      -- product-level summary, reasons, and ingredient breakdown
ProductRecommendation   -- skin-type suitability, precautions, and usage guidance
"""

from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Per-ingredient
# ---------------------------------------------------------------------------


class IngredientExplanation(BaseModel):
    """Deterministic explanation for a single analysed ingredient.

    Each instance pairs the ingredient's identity with its safety
    rating, computed risk level, and a concise reason that justifies
    the classification.
    """

    ingredient_name: str = Field(
        ...,
        description="Official INCI name of the ingredient",
        examples=["Niacinamide"],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description="Safety rating on a 0-10 scale (higher = safer)",
        examples=[9.0],
    )
    risk_level: str = Field(
        ...,
        description=(
            "Risk classification derived from the safety rating. "
            "One of: LOW (>= 8.5), MODERATE (>= 6.5), HIGH (>= 4.5), "
            "VERY_HIGH (< 4.5)."
        ),
        examples=["LOW", "MODERATE", "HIGH", "VERY_HIGH"],
    )
    reason: str = Field(
        ...,
        description=(
            "Single-sentence deterministic reason explaining the "
            "ingredient's risk classification"
        ),
        examples=[
            "This ingredient is generally considered safe.",
            "This ingredient may require caution for sensitive individuals.",
        ],
    )


# ---------------------------------------------------------------------------
# Product-level explanation
# ---------------------------------------------------------------------------


class ProductExplanation(BaseModel):
    """Product-level explanation produced by the ExplanationEngine.

    Groups a natural-language summary, a list of deterministic reasons
    supporting the overall assessment, and the full per-ingredient
    breakdown.
    """

    summary: str = Field(
        ...,
        description=(
            "Natural-language summary of the product's overall "
            "safety profile, tailored to the computed risk level"
        ),
        examples=[
            "This product appears to contain mostly low-risk cosmetic ingredients."
        ],
    )
    reasons: list[str] = Field(
        ...,
        description=(
            "Ordered list of deterministic reasons supporting the "
            "product-level risk assessment"
        ),
        examples=[
            [
                "The overall ingredient safety rating is excellent.",
                "This product contains a large number of ingredients.",
            ]
        ],
    )
    ingredient_explanations: list[IngredientExplanation] = Field(
        ...,
        description="Per-ingredient explanations in analysis order",
        examples=[
            [
                {
                    "ingredient_name": "Niacinamide",
                    "safety_rating": 9.0,
                    "risk_level": "LOW",
                    "reason": "This ingredient is generally considered safe.",
                }
            ]
        ],
    )


# ---------------------------------------------------------------------------
# Product-level recommendation
# ---------------------------------------------------------------------------


class ProductRecommendation(BaseModel):
    """Deterministic recommendation produced by the RecommendationEngine.

    Provides skin-type suitability, precautions derived from the risk
    level and ingredient count, and usage guidance for the product.
    """

    recommended_for: list[str] = Field(
        ...,
        description="List of skin types this product is suitable for",
        examples=[["oily", "combination", "normal"]],
    )
    precautions: list[str] = Field(
        default_factory=list,
        description="Usage precautions derived from risk level and ingredient count",
        examples=[
            [
                "Perform a patch test before first use",
                "Discontinue use if irritation occurs",
            ]
        ],
    )
    usage_guidance: str = Field(
        ...,
        description="Short guidance on how to use the product",
        examples=["Apply to clean skin morning and evening."],
    )


# ---------------------------------------------------------------------------
# Overall analysis
# ---------------------------------------------------------------------------


class OverallAnalysis(BaseModel):
    """Aggregate analysis data for the entire product.

    Combines the numeric overall score and risk classification with
    the ingredient count.  The ``summary`` field is populated by
    the explanation engine.
    """

    overall_score: float = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Weighted-average safety score for the product computed "
            "from all recognised ingredient safety ratings (0-10). "
            "Higher values indicate greater safety."
        ),
        examples=[8.5, 6.7, 9.0],
    )
    overall_risk: str = Field(
        ...,
        description=(
            "Deterministic risk classification derived from the "
            "overall score. One of: LOW (>= 8.5), MODERATE (>= 6.5), "
            "HIGH (>= 4.5), VERY_HIGH (< 4.5)."
        ),
        examples=["LOW", "MODERATE", "HIGH", "VERY_HIGH"],
    )
    ingredient_count: int = Field(
        ...,
        ge=0,
        description=(
            "Number of recognised ingredients that contributed to the "
            "overall score. Ingredients not found in the knowledge base "
            "are excluded from this count."
        ),
        examples=[30, 12, 3],
    )
    summary: str = Field(
        default="",
        description=(
            "Natural-language summary of the product's overall "
            "safety assessment, populated by the ExplanationEngine"
        ),
        examples=[
            "This product appears to contain mostly low-risk cosmetic ingredients."
        ],
    )


# ---------------------------------------------------------------------------
# Top-level result
# ---------------------------------------------------------------------------


class AnalysisResult(BaseModel):
    """Complete output of the AI Ingredient Intelligence Engine.

    Encapsulates the overall scoring, the product-level explanation
    (including per-ingredient breakdown), and all metadata required
    by the API layer to build a full response.
    """

    product_name: str = Field(
        ...,
        description="Display name of the analyzed product or scan",
        examples=["The Ordinary Niacinamide 10% + Zinc 1%"],
    )
    ingredient_count: int = Field(
        ...,
        ge=0,
        description="Total number of ingredients that were analysed",
        examples=[30],
    )
    overall_analysis: OverallAnalysis = Field(
        ...,
        description="Aggregate scoring and risk classification",
        examples=[
            {
                "overall_score": 8.5,
                "overall_risk": "LOW",
                "ingredient_count": 30,
            }
        ],
    )
    product_explanation: ProductExplanation = Field(
        ...,
        description=(
            "Product-level explanation including summary, reasons, "
            "and per-ingredient breakdown"
        ),
        examples=[
            {
                "summary": "This product appears to contain mostly low-risk ingredients.",
                "reasons": ["The overall ingredient safety rating is excellent."],
                "ingredient_explanations": [],
            }
        ],
    )
    recommendations: ProductRecommendation = Field(
        ...,
        description=(
            "Deterministic recommendation including skin-type suitability, "
            "precautions, and usage guidance"
        ),
        examples=[
            {
                "recommended_for": ["oily", "combination", "normal"],
                "precautions": ["Perform a patch test before first use"],
                "usage_guidance": "Apply to clean skin morning and evening.",
            }
        ],
    )
    confidence_score: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "Deterministic confidence score (40-100) reflecting the "
            "reliability of the analysis based on available ingredient data"
        ),
        examples=[85, 100, 55],
    )
    analysis_timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the analysis was performed",
        examples=["2026-07-14T12:00:00Z"],
    )
