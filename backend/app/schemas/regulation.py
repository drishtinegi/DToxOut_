"""
Pydantic schemas for Regulation endpoints.

RegulationCreate   -- inbound payload for POST /admin/regulations
RegulationResponse -- outbound schema for all regulation responses
"""

from pydantic import BaseModel, Field


class RegulationCreate(BaseModel):
    """Request body for creating a new regulation."""

    ingredient_id: str = Field(
        ...,
        description="UUID of the associated ingredient",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    )
    country: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Country or jurisdiction code",
        examples=["US"],
    )
    regulatory_status: str = Field(
        ...,
        description="Regulatory status: APPROVED, RESTRICTED, BANNED, or PENDING_REVIEW",
        examples=["APPROVED"],
    )
    restriction_details: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Details about regulatory restrictions",
        examples=["Approved for use in cosmetic formulations at concentrations up to 5%"],
    )
    source: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Source or reference for the regulation",
        examples=["EU Cosmetics Regulation (EC) No 1223/2009"],
    )


class RegulationResponse(BaseModel):
    """Schema returned for a single regulation."""

    id: str = Field(..., description="UUID of the regulation")
    ingredient_id: str = Field(..., description="UUID of the associated ingredient")
    country: str = Field(..., description="Country or jurisdiction code")
    regulatory_status: str = Field(..., description="Regulatory status")
    restriction_details: str = Field(..., description="Details about regulatory restrictions")
    source: str = Field(..., description="Source or reference for the regulation")
