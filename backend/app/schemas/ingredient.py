"""
Pydantic schemas for Ingredient endpoints.

IngredientCreate   -- inbound payload for POST /admin/ingredients
IngredientResponse -- outbound schema for all ingredient responses
"""

from typing import Optional

from pydantic import BaseModel, Field


class IngredientCreate(BaseModel):
    """Request body for creating a new ingredient."""

    inci_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Official INCI (International Nomenclature of Cosmetic Ingredients) "
            "name. Must be unique across the knowledge base."
        ),
        examples=["Niacinamide"],
    )
    common_name: Optional[str] = Field(
        default=None,
        max_length=200,
        description=(
            "Common consumer-friendly or trade name for the ingredient. "
            "Optional — used for display purposes."
        ),
        examples=["Vitamin B3"],
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description=(
            "Human-readable description of the ingredient, covering its "
            "origin, properties, and role in cosmetic formulations."
        ),
        examples=[
            "A water-soluble form of vitamin B3 that improves skin barrier "
            "function and reduces the appearance of pores."
        ],
    )
    function: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Primary cosmetic function or purpose of the ingredient "
            "(e.g. Solvent, Skin conditioning, Preservative)."
        ),
        examples=["Skin conditioning"],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description=(
            "Numeric safety rating on a 0–10 scale. Higher values indicate "
            "greater safety. 0 = highest concern, 10 = safest."
        ),
        examples=[9.0],
    )
    evidence_level: str = Field(
        ...,
        description=(
            "Strength of scientific evidence supporting the safety profile. "
            "Must be one of: LOW, MODERATE, HIGH, VERY_HIGH."
        ),
        examples=["HIGH"],
    )


class IngredientResponse(BaseModel):
    """Schema returned for a single ingredient."""

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
        description="Common consumer-friendly name",
        examples=["Vitamin B3"],
    )
    description: str = Field(
        ...,
        description="Human-readable description of the ingredient",
        examples=[
            "A water-soluble form of vitamin B3 that improves skin barrier "
            "function and reduces the appearance of pores."
        ],
    )
    function: str = Field(
        ...,
        description="Primary cosmetic function or purpose",
        examples=["Skin conditioning"],
    )
    safety_rating: float = Field(
        ...,
        description="Safety rating on a 0–10 scale (higher = safer)",
        examples=[9.0],
    )
    evidence_level: str = Field(
        ...,
        description="Evidence level: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["HIGH"],
    )
    created_at: str = Field(
        ...,
        description="Timestamp when the ingredient was created (ISO 8601)",
        examples=["2025-01-15T10:30:00.000Z"],
    )
