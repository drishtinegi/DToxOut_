"""
Pydantic schemas for Admin Dashboard endpoints.

DashboardStatsResponse      -- aggregated knowledge base statistics
RiskDistributionResponse    -- risk-level breakdown from SafetyProfile
EvidenceDistributionResponse -- evidence-level breakdown from Ingredient
"""

from pydantic import BaseModel, Field


class DashboardStatsResponse(BaseModel):
    """Aggregated counts and recent-activity metrics for the admin dashboard."""

    users: int = Field(
        ...,
        description="Total number of registered users",
        examples=[152],
    )
    ingredients: int = Field(
        ...,
        description="Total number of ingredients in the knowledge base",
        examples=[1240],
    )
    ingredient_categories: int = Field(
        ...,
        description="Total number of ingredient categories",
        examples=[24],
    )
    ingredient_benefits: int = Field(
        ...,
        description="Total number of ingredient benefits",
        examples=[3800],
    )
    ingredient_aliases: int = Field(
        ...,
        description="Total number of ingredient aliases",
        examples=[2100],
    )
    safety_profiles: int = Field(
        ...,
        description="Total number of safety profiles",
        examples=[980],
    )
    regulations: int = Field(
        ...,
        description="Total number of regulatory entries",
        examples=[4200],
    )
    scientific_references: int = Field(
        ...,
        description="Total number of scientific references",
        examples=[1800],
    )
    scans: int = Field(
        ...,
        description="Total number of product scans performed",
        examples=[5600],
    )
    users_last_7_days: int = Field(
        ...,
        description="Users created within the last 7 days",
        examples=[18],
    )
    scans_last_7_days: int = Field(
        ...,
        description="Scans created within the last 7 days",
        examples=[320],
    )


class RiskLevelCount(BaseModel):
    """A single risk-level bucket with its count."""

    risk_level: str = Field(
        ...,
        description="Risk classification label (LOW, MODERATE, HIGH, VERY_HIGH)",
        examples=["LOW"],
    )
    count: int = Field(
        ...,
        description="Number of safety profiles with this risk level",
        examples=[420],
    )


class RiskDistributionResponse(BaseModel):
    """Distribution of safety profiles across risk levels."""

    total: int = Field(
        ...,
        description="Total number of safety profiles",
        examples=[980],
    )
    distribution: list[RiskLevelCount] = Field(
        ...,
        description="Breakdown of counts per risk level",
    )


class EvidenceLevelCount(BaseModel):
    """A single evidence-level bucket with its count."""

    evidence_level: str = Field(
        ...,
        description="Evidence level label (LOW, MODERATE, HIGH, VERY_HIGH)",
        examples=["HIGH"],
    )
    count: int = Field(
        ...,
        description="Number of ingredients with this evidence level",
        examples=[560],
    )


class EvidenceDistributionResponse(BaseModel):
    """Distribution of ingredients across evidence levels."""

    total: int = Field(
        ...,
        description="Total number of ingredients",
        examples=[1240],
    )
    distribution: list[EvidenceLevelCount] = Field(
        ...,
        description="Breakdown of counts per evidence level",
    )
