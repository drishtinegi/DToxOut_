"""
Admin-only ScientificReference API routes.

Every endpoint in this router requires ADMIN role authorization.
ScientificReference CRUD operations delegate to ScientificReferenceService --
Prisma is never accessed directly from route handlers.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import require_admin
from app.database import get_db
from app.schemas.scientific_reference import (
    ScientificReferenceCreate,
    ScientificReferenceResponse,
)
from app.services.scientific_reference_service import ScientificReferenceService

router = APIRouter(prefix="/admin/scientific-references", tags=["admin"])


# ---------------------------------------------------------------------------
# Dependency: provide a ScientificReferenceService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_service(db: Prisma = Depends(get_db)) -> ScientificReferenceService:
    """Build a ScientificReferenceService per request using the active DB client."""
    return ScientificReferenceService(db)


# ---------------------------------------------------------------------------
# ScientificReference CRUD
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ScientificReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reference(
    payload: ScientificReferenceCreate,
    current_user: User = Depends(require_admin),
    service: ScientificReferenceService = Depends(_get_service),
) -> ScientificReferenceResponse:
    """Create a new scientific reference for an ingredient.

    Admin only.  The referenced ingredient must exist and there must not
    already be a reference with the same title and organization for that
    ingredient.  The publication year must not be in the future, and the
    source URL must be a valid HTTP/HTTPS link.

    Returns **201** on success. Ingredient not found raises **404**,
    duplicate raises **409**, validation errors raise **422**, all via
    global DomainError handler.
    """
    reference = await service.create_reference(
        ingredient_id=payload.ingredient_id,
        title=payload.title,
        organization=payload.organization,
        publication_year=payload.publication_year,
        evidence_summary=payload.evidence_summary,
        source_url=payload.source_url,
    )
    return _to_response(reference)


@router.get("", response_model=list[ScientificReferenceResponse])
async def list_references(
    current_user: User = Depends(require_admin),
    service: ScientificReferenceService = Depends(_get_service),
) -> list[dict]:
    """Return all scientific references.

    Admin only.  Returns a list (may be empty).
    """
    references = await service.get_all_references()
    return [_to_response(r).model_dump() for r in references]


@router.get(
    "/{reference_id}",
    response_model=ScientificReferenceResponse,
)
async def get_reference(
    reference_id: str,
    current_user: User = Depends(require_admin),
    service: ScientificReferenceService = Depends(_get_service),
) -> ScientificReferenceResponse:
    """Return a single scientific reference by ID.

    Admin only.  Returns **200** on success.
    Not found raises **404** via global DomainError handler.
    """
    reference = await service.get_reference_by_id(reference_id)
    return _to_response(reference)


@router.delete(
    "/{reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_reference(
    reference_id: str,
    current_user: User = Depends(require_admin),
    service: ScientificReferenceService = Depends(_get_service),
) -> Response:
    """Delete a scientific reference by ID.

    Admin only.  Returns **204** on success.
    Not found raises **404** via global DomainError handler.
    """
    await service.delete_reference(reference_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(reference) -> ScientificReferenceResponse:
    """Map a Prisma ScientificReference record to the ScientificReferenceResponse schema.

    Handles the camelCase -> snake_case field name conversion.
    """
    return ScientificReferenceResponse(
        id=reference.id,
        ingredient_id=reference.ingredientId,
        title=reference.title,
        organization=reference.organization,
        publication_year=reference.publicationYear,
        evidence_summary=reference.evidenceSummary,
        source_url=reference.sourceUrl,
    )
