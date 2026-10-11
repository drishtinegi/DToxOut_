"""
Pydantic response schemas for the AI Knowledge Engine.

Provides nested models for the full ingredient knowledge response,
including category, safety profile, aliases, benefits, regulations,
and scientific references.

These schemas are intentionally self-contained and do not depend on
the search or ingredient schemas so that each module can evolve
independently.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Nested sub-objects
# ---------------------------------------------------------------------------


class IngredientBasicInfo(BaseModel):
    """Core ingredient fields exposed by the knowledge response.

    Mirrors the flat columns on the ``Ingredient`` table without any
    nested relations.
    """

    id: str = Field(
        ...,
        description="Unique identifier (UUID) of the ingredient",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    )
    inci_name: str = Field(
        ...,
        description="Official INCI name of the ingredient",
        examples=["Niacinamide"],
    )
    common_name: Optional[str] = Field(
        default=None,
        description="Common consumer-friendly or trade name",
        examples=["Vitamin B3"],
    )
    description: str = Field(
        ...,
        description="Human-readable description of the ingredient",
        examples=[
            "A water-soluble form of vitamin B3 with multiple skin benefits"
        ],
    )
    function: str = Field(
        ...,
        description="Cosmetic function / purpose of the ingredient",
        examples=["Skin conditioning"],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description="Safety rating on a 0\u201310 scale (higher = safer)",
        examples=[9.0],
    )
    evidence_level: str = Field(
        ...,
        description="Evidence level: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["HIGH"],
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when the ingredient was created",
        examples=["2026-01-15T10:30:00Z"],
    )


class IngredientCategoryResult(BaseModel):
    """Category details for a matched ingredient.

    ``None`` when the ingredient has no assigned category.
    """

    id: str = Field(
        ...,
        description="Unique identifier (UUID) of the category",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )
    name: str = Field(
        ...,
        description="Human-readable category name",
        examples=["Vitamins"],
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional short description of the category",
        examples=["Vitamin-derived skin actives"],
    )


class SafetyProfileResult(BaseModel):
    """Detailed safety breakdown for a matched ingredient.

    ``None`` when no safety profile has been recorded for the ingredient.
    """

    risk_level: str = Field(
        ...,
        description=(
            "Overall risk classification. "
            "One of LOW, MODERATE, HIGH, VERY_HIGH."
        ),
        examples=["LOW"],
    )
    allergy_risk: str = Field(
        ...,
        description="Free-text allergy risk assessment",
        examples=["Rare; no significant allergenic potential"],
    )
    pregnancy_risk: str = Field(
        ...,
        description="Free-text pregnancy safety assessment",
        examples=["Generally considered safe during pregnancy"],
    )
    acne_risk: str = Field(
        ...,
        description="Free-text acne / comedogenicity assessment",
        examples=["Non-comedogenic; does not clog pores"],
    )
    sensitive_skin_risk: str = Field(
        ...,
        description="Free-text sensitive-skin suitability assessment",
        examples=["Well tolerated by sensitive skin types"],
    )
    explanation: str = Field(
        ...,
        description="Detailed safety explanation",
        examples=[
            "Niacinamide is a well-tolerated form of vitamin B3 "
            "with minimal irritation potential."
        ],
    )


class IngredientBenefitResult(BaseModel):
    """A single benefit entry for a matched ingredient."""

    title: str = Field(
        ...,
        description="Short title for the benefit",
        examples=["Reduces inflammation"],
    )
    description: str = Field(
        ...,
        description="Longer description of the benefit",
        examples=["Helps calm redness and irritation."],
    )


class RegulationResult(BaseModel):
    """Regulatory information for an ingredient in a specific country."""

    country: str = Field(
        ...,
        description="Country or jurisdiction code",
        examples=["US", "EU", "JP"],
    )
    regulatory_status: str = Field(
        ...,
        description=(
            "Regulatory status. "
            "One of APPROVED, RESTRICTED, BANNED, PENDING_REVIEW."
        ),
        examples=["APPROVED"],
    )
    restriction_details: str = Field(
        ...,
        description="Details about restrictions or conditions of use",
        examples=["Allowed up to 5% concentration"],
    )
    source: str = Field(
        ...,
        description="Source of the regulatory information",
        examples=["FDA CFR Title 21"],
    )


class ScientificReferenceResult(BaseModel):
    """A scientific publication referencing the ingredient."""

    title: str = Field(
        ...,
        description="Title of the publication",
        examples=["Efficacy of topical niacinamide in skin aging"],
    )
    organization: str = Field(
        ...,
        description="Publishing organization or journal",
        examples=["Journal of Cosmetic Dermatology"],
    )
    publication_year: int = Field(
        ...,
        description="Year the reference was published",
        examples=[2023],
    )
    evidence_summary: str = Field(
        ...,
        description="Brief summary of the evidence presented",
        examples=[
            "Niacinamide demonstrated significant improvement in "
            "skin barrier function over 12 weeks."
        ],
    )
    source_url: Optional[str] = Field(
        default=None,
        description="URL to the full publication (if available)",
        examples=["https://doi.org/10.1111/jocd.12345"],
    )


# ---------------------------------------------------------------------------
# Top-level knowledge response
# ---------------------------------------------------------------------------


class IngredientKnowledgeResponse(BaseModel):
    """Complete knowledge object for a single ingredient.

    Assembles the core ingredient data with all nested relations:
    category, safety profile, aliases, benefits, regulations, and
    scientific references.  Missing relationships return ``null``
    for one-to-one fields and ``[]`` for collections.
    """

    ingredient: IngredientBasicInfo = Field(
        ...,
        description="Core ingredient data (flat columns)",
    )
    category: Optional[IngredientCategoryResult] = Field(
        default=None,
        description="Ingredient category; null if uncategorised",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names or trade names (empty if none)",
        examples=[["Vitamin B3", "Nicotinamide"]],
    )
    benefits: list[IngredientBenefitResult] = Field(
        default_factory=list,
        description="Known benefits for this ingredient (empty if none)",
    )
    safety_profile: Optional[SafetyProfileResult] = Field(
        default=None,
        description="Detailed safety breakdown; null if not available",
    )
    regulations: list[RegulationResult] = Field(
        default_factory=list,
        description="Regulatory information by country (empty if none)",
    )
    scientific_references: list[ScientificReferenceResult] = Field(
        default_factory=list,
        description="Scientific publications referencing this ingredient (empty if none)",
    )
