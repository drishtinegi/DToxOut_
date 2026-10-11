"""
AI Knowledge Engine — API routes.

Exposes :meth:`IngredientService.get_ingredient_knowledge` and
:class:`KnowledgeBuilder.build` through a public endpoint that returns
a complete knowledge object for a single ingredient.

All business logic lives in :mod:`app.services.ingredient_service`
(data access) and :mod:`app.services.knowledge_builder`
(transformation); this module is a thin adapter between HTTP and
those layers.
"""

from fastapi import APIRouter, Depends, Path, status
from prisma import Prisma

from app.database import get_db
from app.schemas.knowledge import IngredientKnowledgeResponse
from app.services.ingredient_service import IngredientService
from app.services.knowledge_builder import KnowledgeBuilder

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Dependency: provide an IngredientService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> IngredientService:
    """Build an :class:`IngredientService` per request using the active DB client."""
    return IngredientService(db)


# ---------------------------------------------------------------------------
# Single Ingredient Knowledge
# ---------------------------------------------------------------------------


@router.get(
    "/ingredient/{ingredient_id}",
    response_model=IngredientKnowledgeResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete knowledge object for an ingredient",
    description=(
        "Return the full ingredient knowledge record including category, "
        "safety profile, aliases, benefits, regulations, and scientific "
        "references.  All nested relations are included; missing "
        "relationships return null for one-to-one fields and empty "
        "lists for collections."
    ),
    response_description="Complete ingredient knowledge with all nested relations",
    responses={
        200: {
            "description": "Ingredient knowledge returned successfully",
        },
        404: {
            "description": "No ingredient matches the given ID",
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "Ingredient with id "
                            "'d290f1ee-6c54-4b01-90e6-d701748f0851' not found"
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
async def get_ingredient_knowledge(
    ingredient_id: str = Path(
        ...,
        description="UUID of the ingredient to look up",
        examples=["d290f1ee-6c54-4b01-90e6-d701748f0851"],
    ),
    service: IngredientService = Depends(_get_service),
) -> IngredientKnowledgeResponse:
    """Retrieve the complete knowledge object for a single ingredient.

    Returns **200** with the full knowledge response on success.
    Not found raises **404** via global DomainError handler.
    """
    ingredient = await service.get_ingredient_knowledge(ingredient_id)
    return KnowledgeBuilder.build(ingredient)
