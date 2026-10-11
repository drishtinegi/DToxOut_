"""
Pydantic schemas for SafetyProfile endpoints.

SafetyProfileCreateRequest  -- inbound payload for POST /admin/safety-profiles
SafetyProfileUpdateRequest  -- inbound payload for PUT  /admin/safety-profiles/{id}
SafetyProfileResponse       -- outbound schema for all safety profile responses
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Risk classification for a safety profile.

    Mirrors the Prisma ``RiskLevel`` enum defined in ``schema.prisma``
    so that request bodies use a constrained set of allowed values.
    """

    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MIN_TEXT_LENGTH = 5
_MAX_TEXT_LENGTH = 500
_MIN_EXPLANATION_LENGTH = 20
_MAX_EXPLANATION_LENGTH = 2000


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class SafetyProfileCreateRequest(BaseModel):
    """Request body for creating a new safety profile.

    All text fields are trimmed of leading/trailing whitespace before
    validation.  Empty strings after trimming are rejected.
    """

    ingredient_id: str = Field(
        ...,
        description=(
            "UUID of the ingredient to attach this safety profile to. "
            "The ingredient must already exist in the knowledge base."
        ),
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    )
    risk_level: RiskLevel = Field(
        ...,
        description=(
            "Overall risk classification.  Must be one of: "
            "``LOW``, ``MODERATE``, ``HIGH``, ``VERY_HIGH``."
        ),
        examples=["MODERATE"],
    )
    allergy_risk: str = Field(
        ...,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Free-text allergy risk assessment for this ingredient. "
            "Must be between 5 and 500 characters."
        ),
        examples=[
            "May cause contact dermatitis in sensitive individuals"
        ],
    )
    pregnancy_risk: str = Field(
        ...,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Free-text pregnancy safety assessment. "
            "Must be between 5 and 500 characters."
        ),
        examples=["Generally considered safe during pregnancy"],
    )
    acne_risk: str = Field(
        ...,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Free-text acne / comedogenicity assessment. "
            "Must be between 5 and 500 characters."
        ),
        examples=["Non-comedogenic; does not clog pores"],
    )
    sensitive_skin_risk: str = Field(
        ...,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Free-text sensitive-skin suitability assessment. "
            "Must be between 5 and 500 characters."
        ),
        examples=["Well tolerated by sensitive skin types"],
    )
    explanation: str = Field(
        ...,
        min_length=_MIN_EXPLANATION_LENGTH,
        max_length=_MAX_EXPLANATION_LENGTH,
        description=(
            "Detailed safety explanation covering usage guidance, "
            "known interactions, and caveats. "
            "Must be between 20 and 2000 characters."
        ),
        examples=[
            "Niacinamide is a well-tolerated form of vitamin B3 "
            "with minimal irritation potential across all skin types."
        ],
    )

    @field_validator(
        "allergy_risk",
        "pregnancy_risk",
        "acne_risk",
        "sensitive_skin_risk",
        "explanation",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, v: str) -> str:
        """Strip whitespace and reject empty strings.

        Args:
            v: Raw string value from the request body.

        Returns:
            The stripped string.

        Raises:
            ValueError: If the value is empty or contains only whitespace.
        """
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field must not be empty or contain only whitespace")
        return stripped


class SafetyProfileUpdateRequest(BaseModel):
    """Request body for updating an existing safety profile.

    All fields are optional — only provided fields are updated.
    When a field is provided, the same validation rules as
    :class:`SafetyProfileCreateRequest` apply.  All text values
    are trimmed of leading/trailing whitespace before validation.
    """

    risk_level: Optional[RiskLevel] = Field(
        default=None,
        description=(
            "New risk classification.  Must be one of: "
            "``LOW``, ``MODERATE``, ``HIGH``, ``VERY_HIGH``."
        ),
        examples=["HIGH"],
    )
    allergy_risk: Optional[str] = Field(
        default=None,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Updated allergy risk assessment. "
            "Must be between 5 and 500 characters when provided."
        ),
        examples=["Rarely causes allergic reactions"],
    )
    pregnancy_risk: Optional[str] = Field(
        default=None,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Updated pregnancy safety assessment. "
            "Must be between 5 and 500 characters when provided."
        ),
        examples=["Consult a healthcare provider before use during pregnancy"],
    )
    acne_risk: Optional[str] = Field(
        default=None,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Updated acne / comedogenicity assessment. "
            "Must be between 5 and 500 characters when provided."
        ),
        examples=["Low comedogenic potential; safe for acne-prone skin"],
    )
    sensitive_skin_risk: Optional[str] = Field(
        default=None,
        min_length=_MIN_TEXT_LENGTH,
        max_length=_MAX_TEXT_LENGTH,
        description=(
            "Updated sensitive-skin suitability assessment. "
            "Must be between 5 and 500 characters when provided."
        ),
        examples=["May cause mild tingling on very sensitive skin"],
    )
    explanation: Optional[str] = Field(
        default=None,
        min_length=_MIN_EXPLANATION_LENGTH,
        max_length=_MAX_EXPLANATION_LENGTH,
        description=(
            "Updated detailed safety explanation. "
            "Must be between 20 and 2000 characters when provided."
        ),
        examples=[
            "Updated safety assessment based on recent clinical data "
            "confirms low irritation potential."
        ],
    )

    @field_validator(
        "allergy_risk",
        "pregnancy_risk",
        "acne_risk",
        "sensitive_skin_risk",
        "explanation",
        mode="before",
    )
    @classmethod
    def _strip_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Strip whitespace and reject empty strings.

        Args:
            v: Raw string value from the request body (may be ``None``).

        Returns:
            The stripped string, or ``None`` if the input was ``None``.

        Raises:
            ValueError: If the value is empty or contains only whitespace.
        """
        if v is None:
            return v
        if not isinstance(v, str):
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field must not be empty or contain only whitespace")
        return stripped


# ---------------------------------------------------------------------------
# Response Schema
# ---------------------------------------------------------------------------


class SafetyProfileResponse(BaseModel):
    """Schema returned for a single safety profile.

    Timestamps are optional because the Prisma ``SafetyProfile`` model
    does not define ``createdAt`` / ``updatedAt`` columns.
    """

    id: str = Field(
        ...,
        description="UUID of the safety profile record",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )
    ingredient_id: str = Field(
        ...,
        description="UUID of the associated ingredient",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    )
    risk_level: str = Field(
        ...,
        description="Risk classification (LOW, MODERATE, HIGH, or VERY_HIGH)",
        examples=["MODERATE"],
    )
    allergy_risk: str = Field(
        ...,
        description="Allergy risk assessment",
        examples=[
            "May cause contact dermatitis in sensitive individuals"
        ],
    )
    pregnancy_risk: str = Field(
        ...,
        description="Pregnancy safety assessment",
        examples=["Generally considered safe during pregnancy"],
    )
    acne_risk: str = Field(
        ...,
        description="Acne / comedogenicity assessment",
        examples=["Non-comedogenic; does not clog pores"],
    )
    sensitive_skin_risk: str = Field(
        ...,
        description="Sensitive-skin suitability assessment",
        examples=["Well tolerated by sensitive skin types"],
    )
    explanation: str = Field(
        ...,
        description="Detailed safety explanation",
        examples=[
            "Niacinamide is a well-tolerated form of vitamin B3 "
            "with minimal irritation potential across all skin types."
        ],
    )
    created_at: Optional[str] = Field(
        default=None,
        description="Timestamp when the profile was created (ISO 8601, if available)",
        examples=["2025-01-15T10:30:00.000Z"],
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="Timestamp when the profile was last updated (ISO 8601, if available)",
        examples=["2025-06-20T14:45:00.000Z"],
    )
