"""
Admin-only API routes.

Every endpoint in this router requires ADMIN role authorization.
Ingredient CRUD operations delegate to IngredientService — Prisma
is never accessed directly from route handlers.
"""

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import Response
from prisma import Prisma
from prisma.models import Ingredient as IngredientRecord
from prisma.models import User

from app.core.audit import audit_log
from app.core.dependencies import require_admin
from app.database import get_db
from app.schemas.ingredient import IngredientCreate, IngredientResponse
from app.services.ingredient_service import (
    IngredientService,
)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependency: provide an IngredientService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> IngredientService:
    """Build an IngredientService per request using the active DB client."""
    return IngredientService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(ingredient: IngredientRecord) -> IngredientResponse:
    """Map a Prisma Ingredient record to the IngredientResponse schema.

    Handles the camelCase -> snake_case field name conversion.

    Args:
        ingredient: The raw Prisma Ingredient record from the database.

    Returns:
        An :class:`IngredientResponse` suitable for JSON serialisation.
    """
    return IngredientResponse(
        id=ingredient.id,
        inci_name=ingredient.inciName,
        common_name=ingredient.commonName,
        description=ingredient.description,
        function=getattr(ingredient, "function", ""),
        safety_rating=ingredient.safetyRating,
        evidence_level=ingredient.evidenceLevel,
        created_at=ingredient.createdAt.isoformat(),
    )


# ---------------------------------------------------------------------------
# Ingredient CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/ingredients",
    response_model=IngredientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ingredient",
    description=(
        "Add a new cosmetic ingredient to the knowledge base. "
        "The INCI name must be unique — duplicates are rejected with 409."
    ),
    responses={
        201: {
            "description": "Ingredient created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "inci_name": "Niacinamide",
                        "common_name": "Vitamin B3",
                        "description": "Form of vitamin B3 with multiple skin benefits.",
                        "function": "Skin conditioning",
                        "safety_rating": 9.0,
                        "evidence_level": "HIGH",
                        "created_at": "2025-01-15T10:30:00.000Z",
                    }
                }
            },
        },
        409: {
            "description": "Ingredient with this INCI name already exists",
            "content": {
                "application/json": {
                    "example": {"detail": "Ingredient with INCI name 'Niacinamide' already exists"}
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
async def create_ingredient(
    payload: IngredientCreate,
    request: Request,
    current_user: User = Depends(require_admin),
    service: IngredientService = Depends(_get_service),
) -> IngredientResponse:
    """Create a new ingredient in the knowledge base.

    Admin only.  Returns **201** on success.
    Duplicate INCI name raises **409** via global DomainError handler.
    """
    ingredient = await service.create_ingredient(
        inci_name=payload.inci_name,
        common_name=payload.common_name,
        description=payload.description,
        function=payload.function,
        safety_rating=payload.safety_rating,
        evidence_level=payload.evidence_level,
    )
    audit_log(
        action="create_ingredient",
        admin_id=current_user.id,
        target_id=ingredient.id,
        status="success",
        request_id=getattr(request.state, "request_id", None),
    )
    return _to_response(ingredient)


@router.get(
    "/ingredients",
    response_model=list[IngredientResponse],
    summary="List all ingredients",
    description=(
        "Return a paginated list of all ingredients in the knowledge base, "
        "ordered by creation date (newest first)."
    ),
    responses={
        200: {
            "description": "List of ingredients (may be empty)",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                            "inci_name": "Niacinamide",
                            "common_name": "Vitamin B3",
                            "description": "Form of vitamin B3.",
                            "function": "Skin conditioning",
                            "safety_rating": 9.0,
                            "evidence_level": "HIGH",
                            "created_at": "2025-01-15T10:30:00.000Z",
                        }
                    ]
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
    },
)
async def list_ingredients(
    current_user: User = Depends(require_admin),
    service: IngredientService = Depends(_get_service),
) -> list[dict]:
    """Return all ingredients.

    Admin only.  Returns a list (may be empty).
    """
    ingredients = await service.get_all_ingredients()
    return [_to_response(i).model_dump() for i in ingredients]


@router.get(
    "/ingredients/{ingredient_id}",
    response_model=IngredientResponse,
    summary="Get an ingredient by ID",
    description="Retrieve a single ingredient from the knowledge base using its UUID.",
    responses={
        200: {
            "description": "Ingredient found",
            "content": {
                "application/json": {
                    "example": {
                        "id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                        "inci_name": "Niacinamide",
                        "common_name": "Vitamin B3",
                        "description": "Form of vitamin B3.",
                        "function": "Skin conditioning",
                        "safety_rating": 9.0,
                        "evidence_level": "HIGH",
                        "created_at": "2025-01-15T10:30:00.000Z",
                    }
                }
            },
        },
        404: {
            "description": "Ingredient not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Ingredient with id 'd290f1ee-...' not found"}
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
async def get_ingredient(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient to retrieve",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    current_user: User = Depends(require_admin),
    service: IngredientService = Depends(_get_service),
) -> IngredientResponse:
    """Return a single ingredient by ID.

    Admin only.  Returns **200** on success.
    Not found raises **404** via global DomainError handler.
    """
    ingredient = await service.get_ingredient_by_id(ingredient_id)
    return _to_response(ingredient)


@router.delete(
    "/ingredients/{ingredient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete an ingredient",
    description=(
        "Permanently remove an ingredient from the knowledge base. "
        "This action cannot be undone."
    ),
    responses={
        204: {"description": "Ingredient deleted successfully"},
        404: {
            "description": "Ingredient not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Ingredient with id 'd290f1ee-...' not found"}
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
async def delete_ingredient(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient to delete",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    request: Request = None,
    current_user: User = Depends(require_admin),
    service: IngredientService = Depends(_get_service),
) -> Response:
    """Delete an ingredient by ID.

    Admin only.  Returns **204** on success.
    Not found raises **404** via global DomainError handler.
    """
    await service.delete_ingredient(ingredient_id)
    audit_log(
        action="delete_ingredient",
        admin_id=current_user.id,
        target_id=ingredient_id,
        status="success",
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
