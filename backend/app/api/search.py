"""
Ingredient Search API routes.

Exposes :class:`IngredientService.search_ingredient` and
:class:`IngredientService.search_multiple_ingredients` through public
(non-admin) endpoints.

All business logic lives in :mod:`app.services.ingredient_service`;
this module is a thin adapter between HTTP and the service layer.
"""

from dataclasses import asdict
from typing import Union

from fastapi import APIRouter, Depends, Query, Request, Response, status
from prisma import Prisma

from app.core.config import settings
from app.database import get_db
from app.middleware.rate_limiting import limiter
from app.schemas.search import (
    BulkIngredientSearchRequest,
    BulkIngredientSearchResult,
    BulkSearchSummary,
    IngredientBenefitResult,
    IngredientCategoryResult,
    IngredientSearchResult,
    SafetyProfileResult,
)
from app.services.ingredient_service import (
    IngredientService,
    SearchResult,
)

router = APIRouter(prefix="/search", tags=["search"])


# ---------------------------------------------------------------------------
# Dependency: provide an IngredientService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> IngredientService:
    """Build an :class:`IngredientService` per request using the active DB client."""
    return IngredientService(db)


# ---------------------------------------------------------------------------
# Mapping helper — Prisma model -> Pydantic response
# ---------------------------------------------------------------------------


def _map_search_result(result: SearchResult) -> IngredientSearchResult:
    """Convert an internal :class:`SearchResult` to the public response schema.

    This is the **single** place where Prisma model fields are translated
    into Pydantic response fields.  Both the single-search and
    bulk-search endpoints reuse this function to stay DRY.

    Args:
        result: An internal :class:`SearchResult` carrying the fully-loaded
            Prisma :class:`Ingredient` and match metadata.

    Returns:
        A Pydantic :class:`IngredientSearchResult` ready for JSON serialisation.
    """
    ing = result.ingredient

    safety_profile: Union[SafetyProfileResult, None] = None
    if ing.safetyProfile is not None:
        sp = ing.safetyProfile
        safety_profile = SafetyProfileResult(
            risk_level=sp.riskLevel,
            allergy_risk=sp.allergyRisk,
            pregnancy_risk=sp.pregnancyRisk,
            acne_risk=sp.acneRisk,
            sensitive_skin_risk=sp.sensitiveSkinRisk,
            explanation=sp.explanation,
        )

    category: Union[IngredientCategoryResult, None] = None
    if ing.category is not None:
        category = IngredientCategoryResult(
            id=ing.category.id,
            name=ing.category.name,
            description=ing.category.description,
        )

    return IngredientSearchResult(
        id=ing.id,
        inci_name=ing.inciName,
        common_name=ing.commonName,
        description=ing.description,
        function=ing.function,
        safety_rating=ing.safetyRating,
        evidence_level=ing.evidenceLevel,
        category=category,
        safety_profile=safety_profile,
        benefits=[
            IngredientBenefitResult(title=b.title, description=b.description)
            for b in (ing.benefits or [])
        ],
        aliases=[a.alias for a in (ing.aliases or [])],
        matched_by=result.matched_by,
        matched_value=result.matched_value,
    )


# ---------------------------------------------------------------------------
# Single Search
# ---------------------------------------------------------------------------


@router.get(
    "/ingredient",
    response_model=IngredientSearchResult,
    status_code=status.HTTP_200_OK,
    summary="Search for a single ingredient by name or alias",
    description=(
        "Look up a single cosmetic ingredient using a free-text query. "
        "The search is case-insensitive and matches against the INCI name, "
        "common name, or any registered alias \u2014 in that priority order. "
        "Returns the full ingredient record including category, safety "
        "profile, benefits, and aliases."
    ),
    response_description="The matched ingredient with all nested relations",
    responses={
        200: {
            "description": "Ingredient found successfully",
            "content": {
                "application/json": {
                    "examples": {
                        "with_safety_profile": {
                            "summary": "Ingredient with a safety profile",
                            "value": {
                                "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "inci_name": "Niacinamide",
                                "common_name": "Vitamin B3",
                                "description": (
                                    "A water-soluble form of vitamin B3 with "
                                    "multiple skin benefits"
                                ),
                                "function": "Skin conditioning",
                                "safety_rating": 9.2,
                                "evidence_level": "HIGH",
                                "category": {
                                    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                    "name": "Vitamins",
                                    "description": (
                                        "Vitamin-derived skin actives"
                                    ),
                                },
                                "safety_profile": {
                                    "risk_level": "LOW",
                                    "allergy_risk": (
                                        "Rare; no significant allergenic potential"
                                    ),
                                    "pregnancy_risk": (
                                        "Generally considered safe during pregnancy"
                                    ),
                                    "acne_risk": (
                                        "Non-comedogenic; does not clog pores"
                                    ),
                                    "sensitive_skin_risk": (
                                        "Well tolerated by sensitive skin types"
                                    ),
                                    "explanation": (
                                        "Niacinamide is a well-tolerated form "
                                        "of vitamin B3 with minimal irritation "
                                        "potential across all skin types."
                                    ),
                                },
                                "benefits": [
                                    {
                                        "title": "Reduces inflammation",
                                        "description": (
                                            "Helps calm redness and irritation."
                                        ),
                                    }
                                ],
                                "aliases": ["Vitamin B3", "Nicotinamide"],
                                "matched_by": "INCI_NAME",
                                "matched_value": "Niacinamide",
                            },
                        },
                        "without_safety_profile": {
                            "summary": "Ingredient without a safety profile",
                            "value": {
                                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                                "inci_name": "Aqua",
                                "common_name": "Water",
                                "description": (
                                    "Solvent and base for most cosmetic formulations"
                                ),
                                "function": "Solvent",
                                "safety_rating": 10.0,
                                "evidence_level": "VERY_HIGH",
                                "category": None,
                                "safety_profile": None,
                                "benefits": [],
                                "aliases": ["Purified Water", "Deionized Water"],
                                "matched_by": "INCI_NAME",
                                "matched_value": "Aqua",
                            },
                        },
                    },
                }
            },
        },
        404: {
            "description": "No ingredient matches the search query",
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "Ingredient not found for query 'UnknownIngredient'"
                        ),
                    }
                }
            },
        },
        500: {
            "description": "Unexpected server error",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected error occurred"}
                }
            },
        },
    },
)
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def search_ingredient(
    request: Request,
    response: Response,
    query: str = Query(
        ...,
        min_length=1,
        max_length=200,
        description=(
            "Search term (1–200 characters). Whitespace is trimmed "
            "and matching is case-insensitive."
        ),
        examples=["Niacinamide"],
    ),
    service: IngredientService = Depends(_get_service),
) -> IngredientSearchResult:
    """Search for a single ingredient by name or alias.

    Returns **200** with the matched ingredient on success.
    No match raises **404** via global DomainError handler.
    """
    result = await service.search_ingredient(query)
    return _map_search_result(result)


# ---------------------------------------------------------------------------
# Bulk Search
# ---------------------------------------------------------------------------


@router.post(
    "/ingredients",
    response_model=BulkIngredientSearchResult,
    status_code=status.HTTP_200_OK,
    summary="Bulk search for multiple ingredients",
    description=(
        "Look up a list of cosmetic ingredients in a single request. "
        "The search is case-insensitive and matches against the INCI name, "
        "common name, or any registered alias \u2014 in that priority order. "
        "Duplicate and blank entries are handled gracefully. "
        "Ingredients that are not found are reported in the ``not_found`` "
        "list rather than causing an error, making this endpoint ideal "
        "for OCR and barcode-scanning pipelines."
    ),
    response_description=(
        "Bulk search envelope containing ``summary`` counts, ``found`` "
        "ingredients, and ``not_found`` names"
    ),
    responses={
        200: {
            "description": "Bulk search completed (some ingredients may not be found)",
            "content": {
                "application/json": {
                    "examples": {
                        "mixed_results": {
                            "summary": (
                                "Typical response with some found and "
                                "some not found"
                            ),
                            "value": {
                                "summary": {
                                    "total_requested": 4,
                                    "found": 2,
                                    "not_found": 2,
                                },
                                "found": [
                                    {
                                        "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                        "inci_name": "Niacinamide",
                                        "common_name": "Vitamin B3",
                                        "description": (
                                            "A water-soluble form of vitamin B3 "
                                            "with multiple skin benefits"
                                        ),
                                        "function": "Skin conditioning",
                                        "safety_rating": 9.2,
                                        "evidence_level": "HIGH",
                                        "category": {
                                            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                            "name": "Vitamins",
                                            "description": (
                                                "Vitamin-derived skin actives"
                                            ),
                                        },
                                        "safety_profile": {
                                            "risk_level": "LOW",
                                            "allergy_risk": (
                                                "Rare; no significant allergenic potential"
                                            ),
                                            "pregnancy_risk": (
                                                "Generally considered safe during pregnancy"
                                            ),
                                            "acne_risk": (
                                                "Non-comedogenic; does not clog pores"
                                            ),
                                            "sensitive_skin_risk": (
                                                "Well tolerated by sensitive skin types"
                                            ),
                                            "explanation": (
                                                "Niacinamide is a well-tolerated "
                                                "form of vitamin B3 with minimal "
                                                "irritation potential."
                                            ),
                                        },
                                        "benefits": [
                                            {
                                                "title": "Reduces inflammation",
                                                "description": (
                                                    "Helps calm redness and irritation."
                                                ),
                                            }
                                        ],
                                        "aliases": ["Vitamin B3", "Nicotinamide"],
                                        "matched_by": "INCI_NAME",
                                        "matched_value": "Niacinamide",
                                    },
                                    {
                                        "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                                        "inci_name": "Aqua",
                                        "common_name": "Water",
                                        "description": (
                                            "Solvent and base for most cosmetic "
                                            "formulations"
                                        ),
                                        "function": "Solvent",
                                        "safety_rating": 10.0,
                                        "evidence_level": "VERY_HIGH",
                                        "category": None,
                                        "safety_profile": None,
                                        "benefits": [],
                                        "aliases": [
                                            "Purified Water",
                                            "Deionized Water",
                                        ],
                                        "matched_by": "INCI_NAME",
                                        "matched_value": "Aqua",
                                    },
                                ],
                                "not_found": [
                                    "UnknownIngredient1",
                                    "UnknownIngredient2",
                                ],
                            },
                        },
                    },
                }
            },
        },
        422: {
            "description": (
                "Validation error (e.g. empty list, blank entry, "
                "or entry exceeding 200 characters)"
            ),
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "ingredients", 1],
                                "msg": "Ingredient names must not be blank",
                                "type": "value_error",
                            }
                        ]
                    }
                }
            },
        },
        500: {
            "description": "Unexpected server error",
            "content": {
                "application/json": {
                    "example": {"detail": "An unexpected error occurred"}
                }
            },
        },
    },
)
@limiter.limit(settings.RATE_LIMIT_SEARCH)
async def bulk_search_ingredients(
    request: Request,
    response: Response,
    body: BulkIngredientSearchRequest,
    service: IngredientService = Depends(_get_service),
) -> BulkIngredientSearchResult:
    """Bulk-search multiple ingredients by name or alias.

    Always returns **200** for a valid request.  Ingredients that match
    a database record appear in ``found``; those that do not appear in
    ``not_found``.
    """
    result = await service.search_multiple_ingredients(body.ingredients)
    return BulkIngredientSearchResult(
        summary=BulkSearchSummary(**asdict(result.summary)),
        found=[_map_search_result(r) for r in result.found],
        not_found=result.not_found,
    )
