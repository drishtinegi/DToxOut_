"""
Pydantic schemas for ScientificReference endpoints.

ScientificReferenceCreate   -- inbound payload for POST /admin/scientific-references
ScientificReferenceResponse -- outbound schema for all scientific reference responses
"""

from pydantic import BaseModel, Field


class ScientificReferenceCreate(BaseModel):
    """Request body for creating a new scientific reference."""

    ingredient_id: str = Field(
        ...,
        description="UUID of the associated ingredient",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Title of the scientific publication",
        examples=["Safety assessment of niacinamide in cosmetic products"],
    )
    organization: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Publishing organization or journal",
        examples=["Journal of Cosmetic Dermatology"],
    )
    publication_year: int = Field(
        ...,
        description="Year of publication",
        examples=[2023],
    )
    evidence_summary: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Summary of the evidence presented in the reference",
        examples=[
            "Niacinamide demonstrates a favorable safety profile across "
            "multiple clinical studies with no significant adverse events."
        ],
    )
    source_url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="URL to the original publication (HTTP/HTTPS)",
        examples=["https://doi.org/10.1111/jdv.12345"],
    )


class ScientificReferenceResponse(BaseModel):
    """Schema returned for a single scientific reference."""

    id: str = Field(..., description="UUID of the scientific reference")
    ingredient_id: str = Field(..., description="UUID of the associated ingredient")
    title: str = Field(..., description="Title of the scientific publication")
    organization: str = Field(..., description="Publishing organization or journal")
    publication_year: int = Field(..., description="Year of publication")
    evidence_summary: str = Field(..., description="Summary of the evidence presented")
    source_url: str = Field(..., description="URL to the original publication")
