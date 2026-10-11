"""
Pydantic schemas for the Scan Analysis Engine.

ScanRequest              — inbound payload for POST /scan/analyze
IngredientAnalysis       — one recognized ingredient in the response
UnknownIngredient        — one unrecognized ingredient in the response
RecommendationWarning    — a structured warning for a specific concern
ScanRecommendation       — overall recommendation with warnings
ScanResponse             — outbound schema for the scan result
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


_MAX_INGREDIENT_NAME_LENGTH = 200


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Toxicity / risk classification used across ingredients and safety profiles."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class MatchType(str, Enum):
    """Method used to match an input string to a knowledge base entry."""

    EXACT_INCI = "EXACT_INCI"
    EXACT_ALIAS = "EXACT_ALIAS"
    EXACT_COMMON_NAME = "EXACT_COMMON_NAME"
    FUZZY = "FUZZY"
    UNKNOWN = "UNKNOWN"


class EvidenceLevel(str, Enum):
    """Quality of supporting scientific evidence."""

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class RecommendationStatus(str, Enum):
    """Overall product safety recommendation status."""

    SAFE = "SAFE"
    USE_WITH_CAUTION = "USE WITH CAUTION"
    HIGH_RISK = "HIGH RISK"
    AVOID = "AVOID"


MEDICAL_DISCLAIMER = (
    "DToxOut analysis results are informational only and do not constitute a "
    "medical diagnosis or healthcare advice."
)


class ScanRequest(BaseModel):
    """Request body for analyzing a list of cosmetic ingredients."""

    ingredients: list[str] = Field(
        ...,
        min_length=1,
        max_length=300,
        description="List of ingredient names to analyze (1-300 items)",
        examples=[["Water", "Niacinamide", "Panthenol"]],
    )
    selected_jurisdiction: Optional[str] = Field(
        default=None,
        description="Optional jurisdiction code (e.g., 'EU', 'US') to evaluate country-specific regulatory rules",
        examples=["EU"],
    )

    @field_validator("ingredients", mode="before")
    @classmethod
    def validate_ingredients(cls, v: list[str]) -> list[str]:
        """Strip, reject blanks, and enforce max-length per entry.

        Args:
            v: Raw ingredient-name list from the request body.

        Returns:
            Cleaned list with each entry stripped of whitespace.

        Raises:
            ValueError: If any entry is blank after stripping or exceeds
                ``_MAX_INGREDIENT_NAME_LENGTH`` characters.
        """
        cleaned: list[str] = []
        for item in v:
            stripped = item.strip()
            if not stripped:
                raise ValueError("Ingredient names must not be blank")
            if len(stripped) > _MAX_INGREDIENT_NAME_LENGTH:
                raise ValueError(
                    f"Ingredient name exceeds {_MAX_INGREDIENT_NAME_LENGTH} "
                    f"characters"
                )
            cleaned.append(stripped)
        return cleaned


# ---------------------------------------------------------------------------
# Ingredient analysis
# ---------------------------------------------------------------------------


class IngredientAnalysis(BaseModel):
    """Schema for a single recognized ingredient in the scan result."""

    inci_name: str = Field(
        ...,
        description="INCI name of the ingredient",
        examples=["Niacinamide"],
    )
    common_name: Optional[str] = Field(
        default=None,
        description="Common or trade name",
        examples=["Vitamin B3"],
    )
    description: str = Field(
        ...,
        description="Description of the ingredient",
        examples=["Form of vitamin B3 with multiple skin benefits"],
    )
    function: str = Field(
        ...,
        description="Cosmetic function / purpose",
        examples=["Skin conditioning"],
    )
    safety_rating: float = Field(
        ...,
        ge=0,
        le=10,
        description="Safety rating between 0 and 10",
        examples=[9.0],
    )
    evidence_level: str = Field(
        ...,
        description="Evidence level: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["HIGH"],
    )
    risk: str = Field(
        ...,
        description="Risk classification: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["LOW"],
    )

    # Extended Phase 1 matching metadata
    original_detected_input: Optional[str] = Field(
        default=None,
        description="Original ingredient name as provided in the request",
        examples=["vitamin b3"],
    )
    match_type: Optional[str] = Field(
        default=None,
        description="Lookup tier used to identify the ingredient (EXACT_INCI, EXACT_ALIAS, EXACT_COMMON_NAME, FUZZY)",
        examples=["EXACT_COMMON_NAME"],
    )
    match_confidence: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score of the ingredient match (0.0 to 1.0)",
        examples=[1.0],
    )
    manual_confirmation_recommended: bool = Field(
        default=False,
        description="Whether manual confirmation is recommended for this match",
        examples=[False],
    )
    regulations: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Country-specific regulatory data for this ingredient from the knowledge base",
    )
    scientific_references: Optional[list[dict[str, Any]]] = Field(
        default=None,
        description="Peer-reviewed scientific references for this ingredient from the knowledge base",
    )


class UnknownIngredient(BaseModel):
    """Schema for an ingredient that could not be matched in the database."""

    name: str = Field(
        ...,
        description="Raw ingredient name as provided in the request",
        examples=["Fragrance"],
    )
    reason: str = Field(
        ...,
        description="Explanation of why the ingredient is unrecognized",
        examples=["Ingredient not found in knowledge base."],
    )
    match_type: Optional[str] = Field(
        default="UNKNOWN",
        description="Match classification (always UNKNOWN for unrecognized entries)",
        examples=["UNKNOWN"],
    )


# ---------------------------------------------------------------------------
# Recommendation warnings
# ---------------------------------------------------------------------------


class RecommendationWarning(BaseModel):
    """Structured warning generated by the Recommendation Engine.

    Each warning targets a specific safety concern (e.g. pregnancy,
    acne, sensitive skin, allergy) for a single ingredient.
    """

    type: str = Field(
        ...,
        description="Warning category: PREGNANCY, ACNE, SENSITIVE_SKIN, or ALLERGY",
        examples=["PREGNANCY"],
    )
    severity: str = Field(
        ...,
        description="Warning severity: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["HIGH"],
    )
    title: str = Field(
        ...,
        description="Short human-readable warning title",
        examples=["Pregnancy Warning"],
    )
    message: str = Field(
        ...,
        description="Detailed warning message with safety guidance",
        examples=[
            "One or more ingredients may not be suitable during pregnancy."
        ],
    )
    ingredient_name: str = Field(
        ...,
        description="INCI name of the ingredient that triggered this warning",
        examples=["Retinol"],
    )


class ScanRecommendation(BaseModel):
    """Overall recommendation produced by the Recommendation Engine.

    Combines a risk-level-based recommendation label, a user-facing
    message, and any structured warnings derived from ingredient
    safety profiles.
    """

    recommendation: str = Field(
        ...,
        description=(
            "Recommendation label derived from the overall risk level. "
            "One of: SAFE, USE WITH CAUTION, HIGH RISK, AVOID"
        ),
        examples=["SAFE"],
    )
    recommendation_message: str = Field(
        ...,
        description="Human-readable recommendation explanation",
        examples=[
            "This product appears to have a low overall ingredient "
            "risk based on the available data."
        ],
    )
    warnings: list[RecommendationWarning] = Field(
        default_factory=list,
        description="Structured warnings for specific safety concerns",
    )


# ---------------------------------------------------------------------------
# Scan response
# ---------------------------------------------------------------------------


class ScanResponse(BaseModel):
    """Response schema returned by the scan analysis endpoint."""

    overall_score: float = Field(
        ...,
        ge=0,
        le=10,
        description="Aggregate safety score for the product (0-10)",
        examples=[8.5],
    )
    overall_risk: str = Field(
        ...,
        description="Overall risk classification: LOW, MODERATE, HIGH, or VERY_HIGH",
        examples=["LOW"],
    )
    recognized_count: int = Field(
        ...,
        description="Number of ingredients matched in the database",
        examples=[28],
    )
    unknown_count: int = Field(
        ...,
        description="Number of ingredients not found in the database",
        examples=[2],
    )
    recognized_ingredients: list[IngredientAnalysis] = Field(
        ...,
        description="Details for each recognized ingredient",
        examples=[
            [
                {
                    "inci_name": "Niacinamide",
                    "common_name": "Vitamin B3",
                    "description": "Form of vitamin B3 with multiple skin benefits",
                    "function": "Skin conditioning",
                    "safety_rating": 9.0,
                    "evidence_level": "HIGH",
                    "risk": "LOW",
                }
            ]
        ],
    )
    unknown_ingredients: list[UnknownIngredient] = Field(
        ...,
        description="Ingredients that could not be matched in the database",
        examples=[
            [
                {
                    "name": "Fragrance",
                    "reason": "Ingredient not found in knowledge base.",
                }
            ]
        ],
    )
    analysis_summary: str = Field(
        ...,
        description="Human-readable summary of the analysis",
        examples=[
            "This product is generally safe. 28 of 30 ingredients were recognized."
        ],
    )
    recommendation: str = Field(
        ...,
        description=(
            "Recommendation label from the Recommendation Engine. "
            "One of: SAFE, USE WITH CAUTION, HIGH RISK, AVOID"
        ),
        examples=["SAFE"],
    )
    recommendation_message: str = Field(
        ...,
        description="Human-readable recommendation explanation",
        examples=[
            "This product appears to have a low overall ingredient "
            "risk based on the available data."
        ],
    )
    warnings: list[RecommendationWarning] = Field(
        default_factory=list,
        description="Structured warnings for specific safety concerns",
    )
    recognition_coverage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Percentage of submitted unique ingredients successfully matched (0.0 to 100.0%)",
        examples=[93.33],
    )
    disclaimer: Optional[str] = Field(
        default=MEDICAL_DISCLAIMER,
        description="Informational disclaimer stating analysis results are for reference and not a medical diagnosis",
        examples=[MEDICAL_DISCLAIMER],
    )

    # ------------------------------------------------------------------
    # Extended analysis fields (populated by the Analysis sub-package)
    # ------------------------------------------------------------------

    confidence_score: Optional[int] = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Deterministic confidence score (40-100) reflecting the "
            "reliability of the analysis based on available ingredient data. "
            "Populated by the AnalysisEngine's ConfidenceEngine."
        ),
        examples=[85],
    )
    analysis_timestamp: Optional[datetime] = Field(
        default=None,
        description="UTC timestamp when the extended analysis was performed",
        examples=["2026-07-14T12:00:00Z"],
    )
    explanation_summary: Optional[str] = Field(
        default=None,
        description=(
            "Natural-language summary of the product's overall safety "
            "profile, generated by the ExplanationEngine"
        ),
        examples=[
            "This product appears to contain mostly low-risk cosmetic ingredients."
        ],
    )
    explanation_reasons: Optional[list[str]] = Field(
        default=None,
        description=(
            "Ordered list of deterministic reasons supporting the "
            "product-level risk assessment, generated by the ExplanationEngine"
        ),
        examples=[
            [
                "The overall ingredient safety rating is excellent.",
                "This product contains a large number of ingredients.",
            ]
        ],
    )
    recommended_for: Optional[list[str]] = Field(
        default=None,
        description=(
            "List of skin types this product is suitable for, "
            "generated by the AnalysisEngine's RecommendationEngine"
        ),
        examples=[["oily", "combination", "normal"]],
    )
    precautions: Optional[list[str]] = Field(
        default=None,
        description=(
            "Usage precautions derived from risk level and ingredient count, "
            "generated by the AnalysisEngine's RecommendationEngine"
        ),
        examples=[
            [
                "Perform a patch test before first use",
                "Discontinue use if irritation occurs",
            ]
        ],
    )
    usage_guidance: Optional[str] = Field(
        default=None,
        description=(
            "Short guidance on how to use the product, "
            "generated by the AnalysisEngine's RecommendationEngine"
        ),
        examples=["Apply to clean skin morning and evening."],
    )
    ingredient_explanations: Optional[list[dict]] = Field(
        default=None,
        description=(
            "Per-ingredient explanations with risk_level and reason, "
            "generated by the ExplanationEngine"
        ),
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
# OCR Preparation Schemas
# ---------------------------------------------------------------------------


class OCRPrepareRequest(BaseModel):
    """Inbound request payload for POST /api/v1/scan/prepare-text."""

    raw_text: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Raw OCR-extracted text from image or label scan",
        examples=["Active Ingredients: Salicylic Acid (2.0%)\nInactive: Water, Glycerin"],
    )


class OCRMatchDetail(BaseModel):
    """Match status detail for a candidate term in OCR text prep."""

    candidate_term: str = Field(..., description="Extracted candidate ingredient term")
    match_type: str = Field(..., description="Match status: EXACT_INCI, EXACT_ALIAS, EXACT_COMMON_NAME, FUZZY, UNKNOWN")
    matched_inci: Optional[str] = Field(default=None, description="Matched canonical INCI name if resolved")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Match confidence (0.0 - 1.0)")
    manual_confirmation_recommended: bool = Field(default=False, description="True if term requires user review")
    reason: str = Field(..., description="Explanation of match resolution")


class OCRPrepareResponse(BaseModel):
    """Outbound response payload for POST /api/v1/scan/prepare-text."""

    raw_text: str = Field(..., description="Original raw OCR text input")
    cleaned_text: str = Field(..., description="Cleaned, normalized ingredient string")
    candidate_terms: list[str] = Field(..., description="List of segmented candidate terms")
    match_details: list[OCRMatchDetail] = Field(..., description="Match details for candidate terms")
    parser_confidence: float = Field(..., ge=0.0, le=100.0, description="Estimated OCR parsing confidence percentage (0-100)")
    review_required: bool = Field(..., description="True if parser confidence < 75% or high unrecognized term ratio")
    warnings: list[str] = Field(default_factory=list, description="Warnings or notifications regarding OCR text quality")
    candidate_count: int = Field(..., description="Total candidate terms extracted")
    recognized_count: int = Field(..., description="Number of candidate terms matched to knowledge base")
    unknown_count: int = Field(..., description="Number of candidate terms remaining unrecognized")


# ---------------------------------------------------------------------------
# Image Upload & Processing Schemas (Phase 4)
# ---------------------------------------------------------------------------


class ImageUploadResponse(BaseModel):
    """Response schema for POST /api/v1/scan/upload-image."""

    upload_id: str = Field(..., description="Unique UUID for the uploaded image session")
    safe_filename: str = Field(..., description="Server-generated safe filename (no path)")
    media_type: str = Field(..., description="Validated MIME type (image/jpeg, image/png, image/webp)")
    file_size: int = Field(..., description="File size in bytes")
    status: str = Field(default="success", description="Upload status")


class ImageProcessRequest(BaseModel):
    """Request payload for POST /api/v1/scan/process-image."""

    upload_id: str = Field(..., description="UUID of the uploaded image file to process")


class ImageProcessResponse(BaseModel):
    """Response schema for POST /api/v1/scan/process-image."""

    upload_id: str = Field(..., description="UUID of the processed image file")
    raw_text: str = Field(..., description="Raw text extracted by the OCR engine")
    cleaned_text: str = Field(..., description="Cleaned, normalized text")
    candidate_terms: list[str] = Field(..., description="Segmented candidate terms for review")
    match_details: list[OCRMatchDetail] = Field(..., description="Match resolution details for candidate terms")
    ocr_provider: str = Field(..., description="Name of active OCR engine provider used")
    ocr_confidence: float = Field(..., ge=0.0, le=1.0, description="OCR engine confidence (0.0 to 1.0)")
    parser_confidence: float = Field(..., ge=0.0, le=100.0, description="OCR parsing confidence score (0 to 100)")
    processing_duration_ms: float = Field(default=0.0, description="OCR processing duration in milliseconds")
    review_required: bool = Field(..., description="True if manual term review is recommended")
    warnings: list[str] = Field(default_factory=list, description="Warnings or quality alerts")
    recognized_count: int = Field(..., description="Recognized candidate terms count")
    unknown_count: int = Field(..., description="Unknown candidate terms count")

