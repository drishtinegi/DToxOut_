"""
Pydantic schemas for the Scan History API.

ScanCreateRequest       — inbound payload for POST /scan/history
ScanIngredientResponse  — one detected ingredient inside a saved scan
ScanResponse            — outbound schema for a single saved scan
ScanListResponse        — paginated list of saved scans
"""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ScanCreateRequest(BaseModel):
    """Request body for saving a new product scan."""

    product_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Display name of the scanned product",
        examples=["The Ordinary Niacinamide 10% + Zinc 1%"],
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL of the product image, if available",
        examples=["https://example.com/product.jpg"],
    )
    overall_risk_score: float = Field(
        ...,
        ge=0,
        le=10,
        description="Aggregate safety score for the product (0-10)",
        examples=[8.5],
    )


# ---------------------------------------------------------------------------
# Ingredient detail
# ---------------------------------------------------------------------------


class ScanIngredientResponse(BaseModel):
    """Schema for a single detected ingredient within a saved scan."""

    ingredient_id: str = Field(
        ...,
        description="UUID of the matched Ingredient in the knowledge base",
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
    detected_name: str = Field(
        ...,
        description="Raw ingredient name as detected by the analysis engine",
        examples=["Niacinamide"],
    )
    confidence_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Detection confidence score between 0.0 and 1.0",
        examples=[0.95],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description="Safety rating on a 0-10 scale (higher = safer)",
        examples=[9.0],
    )
    evidence_level: str = Field(
        ...,
        description="Evidence level: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["HIGH"],
    )


# ---------------------------------------------------------------------------
# Scan response
# ---------------------------------------------------------------------------


class ScanResponse(BaseModel):
    """Response schema for a single saved scan with its ingredients."""

    id: str = Field(
        ...,
        description="Unique identifier (UUID) of the scan",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )
    product_name: str = Field(
        ...,
        description="Display name of the scanned product",
        examples=["The Ordinary Niacinamide 10% + Zinc 1%"],
    )
    image_url: Optional[str] = Field(
        default=None,
        description="URL of the product image, if available",
        examples=["https://example.com/product.jpg"],
    )
    overall_risk_score: float = Field(
        ...,
        ge=0,
        le=10,
        description="Aggregate safety score for the product (0-10)",
        examples=[8.5],
    )
    created_at: str = Field(
        ...,
        description="Timestamp when the scan was created (ISO 8601)",
        examples=["2025-06-15T14:30:00.000Z"],
    )
    ingredients: list[ScanIngredientResponse] = Field(
        default_factory=list,
        description="Detected ingredients associated with this scan",
        examples=[
            [
                {
                    "ingredient_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                    "inci_name": "Niacinamide",
                    "common_name": "Vitamin B3",
                    "detected_name": "Niacinamide",
                    "confidence_score": 0.95,
                    "safety_rating": 9.0,
                    "evidence_level": "HIGH",
                }
            ]
        ],
    )


# ---------------------------------------------------------------------------
# Paginated list
# ---------------------------------------------------------------------------


class ScanListResponse(BaseModel):
    """Paginated response containing multiple saved scans."""

    items: list[ScanResponse] = Field(
        ...,
        description="List of saved scans for the current page",
        examples=[
            [
                {
                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "product_name": "The Ordinary Niacinamide 10% + Zinc 1%",
                    "image_url": "https://example.com/product.jpg",
                    "overall_risk_score": 8.5,
                    "created_at": "2025-06-15T14:30:00.000Z",
                    "ingredients": [],
                }
            ]
        ],
    )
    total: int = Field(
        ...,
        description="Total number of scans belonging to the user",
        examples=[42],
    )
    skip: int = Field(
        ...,
        description="Number of records skipped for this page",
        examples=[0],
    )
    limit: int = Field(
        ...,
        description="Maximum number of records returned per page",
        examples=[20],
    )
