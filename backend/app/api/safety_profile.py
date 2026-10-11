"""
Admin-only SafetyProfile API routes.

Every endpoint in this router requires ADMIN role authorization.
SafetyProfile CRUD operations delegate to SafetyProfileService --
Prisma is never accessed directly from route handlers.
"""

from fastapi import APIRouter, Depends, Path, status
from fastapi.responses import Response
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import require_admin
from app.database import get_db
from app.schemas.safety_profile import (
    SafetyProfileCreateRequest,
    SafetyProfileResponse,
    SafetyProfileUpdateRequest,
)
from app.services.safety_profile_service import (
    SafetyProfileService,
)

router = APIRouter(prefix="/admin/safety-profiles", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependency: provide a SafetyProfileService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> SafetyProfileService:
    """Build a SafetyProfileService per request using the active DB client."""
    return SafetyProfileService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(profile) -> SafetyProfileResponse:
    """Map a Prisma SafetyProfile record to the SafetyProfileResponse schema.

    Handles the camelCase -> snake_case field name conversion.

    Args:
        profile: The raw Prisma SafetyProfile record from the database.

    Returns:
        A :class:`SafetyProfileResponse` suitable for JSON serialisation.
    """
    return SafetyProfileResponse(
        id=profile.id,
        ingredient_id=profile.ingredientId,
        risk_level=profile.riskLevel,
        allergy_risk=profile.allergyRisk,
        pregnancy_risk=profile.pregnancyRisk,
        acne_risk=profile.acneRisk,
        sensitive_skin_risk=profile.sensitiveSkinRisk,
        explanation=profile.explanation,
    )


# ---------------------------------------------------------------------------
# SafetyProfile CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=SafetyProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new safety profile",
    description=(
        "Create a detailed safety profile for an existing ingredient. "
        "Each ingredient may have at most one safety profile — duplicates "
        "are rejected with 409. The referenced ingredient must exist."
    ),
    responses={
        201: {
            "description": "Safety profile created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "ingredient_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "risk_level": "LOW",
                        "allergy_risk": "Rare",
                        "pregnancy_risk": "Safe",
                        "acne_risk": "Non-comedogenic",
                        "sensitive_skin_risk": "Well tolerated",
                        "explanation": "Generally considered safe for all skin types.",
                    }
                }
            },
        },
        404: {
            "description": "Referenced ingredient not found",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Ingredient with id 'd290f1ee-...' not found"
                    }
                }
            },
        },
        409: {
            "description": "Safety profile already exists for this ingredient",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Safety profile already exists for ingredient 'd290f1ee-...'"
                    }
                }
            },
        },
        403: {
            "description": "Admin access required",
            "content": {
                "application/json": {
                    "example": {"detail": "Administrator access required."}
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
async def create_safety_profile(
    payload: SafetyProfileCreateRequest,
    current_user: User = Depends(require_admin),
    service: SafetyProfileService = Depends(_get_service),
) -> SafetyProfileResponse:
    """Create a new safety profile for an ingredient.

    Admin only.  The referenced ingredient must exist and must not
    already have a safety profile.

    Returns **201** on success. Ingredient not found raises **404**,
    duplicate raises **409**, both via global DomainError handler.
    """
    profile = await service.create_safety_profile(
        ingredient_id=payload.ingredient_id,
        risk_level=payload.risk_level,
        allergy_risk=payload.allergy_risk,
        pregnancy_risk=payload.pregnancy_risk,
        acne_risk=payload.acne_risk,
        sensitive_skin_risk=payload.sensitive_skin_risk,
        explanation=payload.explanation,
    )
    return _to_response(profile)


@router.get(
    "/{ingredient_id}",
    response_model=SafetyProfileResponse,
    summary="Get a safety profile by ingredient ID",
    description=(
        "Retrieve the safety profile for a specific ingredient using "
        "the ingredient's UUID."
    ),
    responses={
        200: {
            "description": "Safety profile found",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "ingredient_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "risk_level": "LOW",
                        "allergy_risk": "Rare",
                        "pregnancy_risk": "Safe",
                        "acne_risk": "Non-comedogenic",
                        "sensitive_skin_risk": "Well tolerated",
                        "explanation": "Generally considered safe for all skin types.",
                    }
                }
            },
        },
        404: {
            "description": "Safety profile not found for this ingredient",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Safety profile not found for ingredient 'd290f1ee-...'"
                    }
                }
            },
        },
        403: {
            "description": "Admin access required",
            "content": {
                "application/json": {
                    "example": {"detail": "Administrator access required."}
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
async def get_safety_profile(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient whose safety profile to retrieve",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    current_user: User = Depends(require_admin),
    service: SafetyProfileService = Depends(_get_service),
) -> SafetyProfileResponse:
    """Get a safety profile by ingredient ID.

    Admin only.  Returns **200** on success.
    Not found raises **404** via global DomainError handler.
    """
    profile = await service.get_safety_profile_by_ingredient(ingredient_id)
    return _to_response(profile)


@router.put(
    "/{ingredient_id}",
    response_model=SafetyProfileResponse,
    summary="Update a safety profile",
    description=(
        "Update an existing safety profile for a specific ingredient. "
        "Only provided fields are updated — omitted fields remain unchanged. "
        "The safety profile must already exist."
    ),
    responses={
        200: {
            "description": "Safety profile updated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "ingredient_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "risk_level": "HIGH",
                        "allergy_risk": "Rare",
                        "pregnancy_risk": "Safe",
                        "acne_risk": "Non-comedogenic",
                        "sensitive_skin_risk": "Well tolerated",
                        "explanation": "Updated safety assessment based on recent clinical data.",
                    }
                }
            },
        },
        404: {
            "description": "Safety profile not found for this ingredient",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Safety profile not found for ingredient 'd290f1ee-...'"
                    }
                }
            },
        },
        403: {
            "description": "Admin access required",
            "content": {
                "application/json": {
                    "example": {"detail": "Administrator access required."}
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
async def update_safety_profile(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient whose safety profile to update",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    payload: SafetyProfileUpdateRequest = ...,
    current_user: User = Depends(require_admin),
    service: SafetyProfileService = Depends(_get_service),
) -> SafetyProfileResponse:
    """Update a safety profile by ingredient ID.

    Admin only.  Only non-null fields in the request body are applied.
    Returns **200** on success.
    Not found raises **404** via global DomainError handler.
    """
    profile = await service.update_safety_profile(
        ingredient_id=ingredient_id,
        risk_level=payload.risk_level,
        allergy_risk=payload.allergy_risk,
        pregnancy_risk=payload.pregnancy_risk,
        acne_risk=payload.acne_risk,
        sensitive_skin_risk=payload.sensitive_skin_risk,
        explanation=payload.explanation,
    )
    return _to_response(profile)


@router.delete(
    "/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a safety profile",
    description=(
        "Permanently remove the safety profile for a specific ingredient. "
        "This action cannot be undone."
    ),
    responses={
        204: {"description": "Safety profile deleted successfully"},
        404: {
            "description": "Safety profile not found for this ingredient",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Safety profile not found for ingredient 'd290f1ee-...'"
                    }
                }
            },
        },
        403: {
            "description": "Admin access required",
            "content": {
                "application/json": {
                    "example": {"detail": "Administrator access required."}
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
async def delete_safety_profile(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient whose safety profile to delete",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    current_user: User = Depends(require_admin),
    service: SafetyProfileService = Depends(_get_service),
) -> Response:
    """Delete a safety profile by ingredient ID.

    Admin only.  Returns **204** on success.
    Not found raises **404** via global DomainError handler.
    """
    await service.delete_safety_profile(ingredient_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
