"""
Pydantic schemas for the Ingredient Search Engine.

Single Search
    IngredientSearchRequest        -- inbound query for GET /search/ingredient
    IngredientSearchResult         -- outbound schema for a matched ingredient

Bulk Search
    BulkIngredientSearchRequest    -- inbound body for POST /search/ingredients
    BulkSearchSummary              -- aggregate counts for the bulk response
    BulkIngredientSearchResult     -- outbound envelope for bulk search

Nested / Shared
    IngredientCategoryResult       -- category sub-object on a search result
    SafetyProfileResult            -- safety-profile sub-object on a search result
    IngredientBenefitResult        -- benefit sub-object on a search result
    MatchedBy                      -- enum indicating which field produced a match
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MatchedBy(str, Enum):
    """Indicator of which knowledge-base field produced the match.

    Used in both single and bulk search responses so that consumers
    can distinguish between an INCI-name hit, a common-name hit, and
    an alias hit without inspecting the ``matched_value`` string.
    """

    INCI_NAME = "INCI_NAME"
    COMMON_NAME = "COMMON_NAME"
    ALIAS = "ALIAS"


# ---------------------------------------------------------------------------
# Single Search — Request
# ---------------------------------------------------------------------------


class IngredientSearchRequest(BaseModel):
    """Query parameters for ``GET /search/ingredient``.

    This schema is intentionally lightweight; FastAPI validates the
    ``query`` query-parameter inline, but defining the schema here
    keeps the OpenAPI ``components/schemas`` section explicit.
    """

    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Search term used to look up an ingredient. "
            "Whitespace is trimmed automatically and matching is "
            "case-insensitive."
        ),
        examples=["Niacinamide"],
    )


# ---------------------------------------------------------------------------
# Single Search — Response (nested sub-objects)
# ---------------------------------------------------------------------------


class IngredientCategoryResult(BaseModel):
    """Category details for a matched ingredient.

    Returned as a nested object inside :class:`IngredientSearchResult`.
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

    Returned as a nested object inside :class:`IngredientSearchResult`.
    ``None`` when no safety profile has been recorded for the ingredient.

    All six fields are guaranteed to be present when the profile exists,
    because the underlying Prisma ``SafetyProfile`` model defines every
    column as non-nullable.
    """

    risk_level: str = Field(
        ...,
        description=(
            "Overall risk classification.  "
            "One of ``LOW``, ``MODERATE``, ``HIGH``, ``VERY_HIGH``."
        ),
        examples=["LOW"],
    )
    allergy_risk: str = Field(
        ...,
        description=(
            "Free-text allergy risk assessment describing the likelihood "
            "and severity of allergic reactions."
        ),
        examples=["Rare; no significant allergenic potential"],
    )
    pregnancy_risk: str = Field(
        ...,
        description=(
            "Free-text pregnancy safety assessment describing usage "
            "guidance during pregnancy and breastfeeding."
        ),
        examples=["Generally considered safe during pregnancy"],
    )
    acne_risk: str = Field(
        ...,
        description=(
            "Free-text acne / comedogenicity assessment describing the "
            "likelihood of clogging pores or triggering breakouts."
        ),
        examples=["Non-comedogenic; does not clog pores"],
    )
    sensitive_skin_risk: str = Field(
        ...,
        description=(
            "Free-text sensitive-skin suitability assessment describing "
            "tolerance and potential for irritation."
        ),
        examples=["Well tolerated by sensitive skin types"],
    )
    explanation: str = Field(
        ...,
        description=(
            "Detailed safety explanation covering known interactions, "
            "contraindications, and overall usage guidance."
        ),
        examples=[
            "Niacinamide is a well-tolerated form of vitamin B3 "
            "with minimal irritation potential across all skin types."
        ],
    )


class IngredientBenefitResult(BaseModel):
    """A single benefit entry for a matched ingredient.

    Returned as an element of the ``benefits`` list inside
    :class:`IngredientSearchResult`.
    """

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


# ---------------------------------------------------------------------------
# Single Search — Response (top-level)
# ---------------------------------------------------------------------------


class IngredientSearchResult(BaseModel):
    """Response schema for a single matched ingredient.

    Returned by both ``GET /search/ingredient`` (directly) and
    ``POST /search/ingredients`` (as an element of the ``found`` list).
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
    function: Optional[str] = Field(
        default=None,
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
    category: Optional[IngredientCategoryResult] = Field(
        default=None,
        description="Ingredient category; ``null`` if uncategorised",
    )
    safety_profile: Optional[SafetyProfileResult] = Field(
        default=None,
        description="Detailed safety breakdown; ``null`` if not available",
    )
    benefits: list[IngredientBenefitResult] = Field(
        default_factory=list,
        description="Known benefits for this ingredient (empty list if none)",
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names or trade names (empty list if none)",
    )
    matched_by: MatchedBy = Field(
        ...,
        description=(
            "Which field produced the match: "
            "``INCI_NAME``, ``COMMON_NAME``, or ``ALIAS``."
        ),
        examples=["INCI_NAME"],
    )
    matched_value: str = Field(
        ...,
        description="The actual text value that matched the query",
        examples=["Niacinamide"],
    )


# ---------------------------------------------------------------------------
# Bulk Search — Request
# ---------------------------------------------------------------------------

_MAX_INGREDIENT_NAME_LENGTH = 200


class BulkIngredientSearchRequest(BaseModel):
    """Request body for ``POST /search/ingredients``.

    Accepts a list of ingredient names (1\u2013100 items).  Each entry
    is stripped of leading/trailing whitespace and validated for
    non-emptiness and maximum length before any database lookup.
    """

    ingredients: list[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description=(
            "List of ingredient names to look up (1\u2013100 items). "
            "Each entry is trimmed and must be non-empty."
        ),
        examples=[
            ["Niacinamide", "Glycerin", "Panthenol", "Water", "Fragrance"],
        ],
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
                    f"characters: '{stripped[:50]}...'"
                )
            cleaned.append(stripped)
        return cleaned


# ---------------------------------------------------------------------------
# Bulk Search — Response
# ---------------------------------------------------------------------------


class BulkSearchSummary(BaseModel):
    """Aggregate counts returned alongside the bulk search results.

    ``total_requested`` reflects the number of **unique** (post-dedup)
    ingredient names that were actually queried.
    """

    total_requested: int = Field(
        ...,
        description=(
            "Number of unique ingredient names queried "
            "(duplicates removed)"
        ),
        examples=[5],
    )
    found: int = Field(
        ...,
        description="Number of unique ingredients that matched a record",
        examples=[3],
    )
    not_found: int = Field(
        ...,
        description="Number of unique ingredients that did not match",
        examples=[2],
    )


class BulkIngredientSearchResult(BaseModel):
    """Response envelope for ``POST /search/ingredients``.

    Always returns HTTP 200.  Ingredients that match a database record
    appear in ``found``; those that do not appear in ``not_found``.
    Request order (including duplicates) is preserved in both lists.
    """

    summary: BulkSearchSummary = Field(
        ...,
        description="Aggregate counts for this request",
    )
    found: list[IngredientSearchResult] = Field(
        default_factory=list,
        description="Ingredients that were successfully found",
    )
    not_found: list[str] = Field(
        default_factory=list,
        description=(
            "Original ingredient names that did not match any record; "
            "request order is preserved."
        ),
        examples=[["Water", "Fragrance"]],
    )
