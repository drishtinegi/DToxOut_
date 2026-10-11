"""
Admin-only Regulation API routes.

Every endpoint in this router requires ADMIN role authorization.
Regulation CRUD operations delegate to RegulationService --
Prisma is never accessed directly from route handlers.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import require_admin
from app.database import get_db
from app.schemas.regulation import RegulationCreate, RegulationResponse
from app.services.regulation_service import RegulationService

router = APIRouter(prefix="/admin/regulations", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependency: provide a RegulationService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> RegulationService:
    """Build a RegulationService per request using the active DB client."""
    return RegulationService(db)


# ---------------------------------------------------------------------------
# Regulation CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=RegulationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_regulation(
    payload: RegulationCreate,
    current_user: User = Depends(require_admin),
    service: RegulationService = Depends(_get_service),
) -> RegulationResponse:
    """Create a new regulation for an ingredient in a country.

    Admin only.  The referenced ingredient must exist and there must not
    already be a regulation for the same ingredient-country pair.

    Returns **201** on success. Ingredient not found raises **404**,
    duplicate raises **409**, both via global DomainError handler.
    """
    regulation = await service.create_regulation(
        ingredient_id=payload.ingredient_id,
        country=payload.country,
        regulatory_status=payload.regulatory_status,
        restriction_details=payload.restriction_details,
        source=payload.source,
    )
    return _to_response(regulation)


@router.get("", response_model=list[RegulationResponse])
async def list_regulations(
    current_user: User = Depends(require_admin),
    service: RegulationService = Depends(_get_service),
) -> list[dict]:
    """Return all regulations.

    Admin only.  Returns a list (may be empty).
    """
    regulations = await service.get_all_regulations()
    return [_to_response(r).model_dump() for r in regulations]


@router.get(
    "/{regulation_id}",
    response_model=RegulationResponse,
)
async def get_regulation(
    regulation_id: str,
    current_user: User = Depends(require_admin),
    service: RegulationService = Depends(_get_service),
) -> RegulationResponse:
    """Return a single regulation by ID.

    Admin only.  Returns **200** on success.
    Not found raises **404** via global DomainError handler.
    """
    regulation = await service.get_regulation_by_id(regulation_id)
    return _to_response(regulation)


@router.delete(
    "/{regulation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_regulation(
    regulation_id: str,
    current_user: User = Depends(require_admin),
    service: RegulationService = Depends(_get_service),
) -> Response:
    """Delete a regulation by ID.

    Admin only.  Returns **204** on success.
    Not found raises **404** via global DomainError handler.
    """
    await service.delete_regulation(regulation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(regulation) -> RegulationResponse:
    """Map a Prisma Regulation record to the RegulationResponse schema.

    Handles the camelCase -> snake_case field name conversion.
    """
    return RegulationResponse(
        id=regulation.id,
        ingredient_id=regulation.ingredientId,
        country=regulation.country,
        regulatory_status=regulation.regulatoryStatus,
        restriction_details=regulation.restrictionDetails,
        source=regulation.source,
    )
