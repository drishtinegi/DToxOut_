"""
Scan History API routes.

Exposes CRUD endpoints for managing user scan history.
All business logic lives in ScanService — this module is a thin adapter
between HTTP and the service layer.
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import Response
from prisma import Prisma
from prisma.models import Scan as PrismaScan
from prisma.models import User

from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.scan_history import (
    ScanCreateRequest,
    ScanIngredientResponse,
    ScanListResponse,
    ScanResponse,
)
from app.services.scan_service import ScanService

router = APIRouter(prefix="/scans", tags=["Scan History"])


# ---------------------------------------------------------------------------
# Dependency: provide a ScanService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_scan_service(db: Prisma = Depends(get_db)) -> ScanService:
    """Build a ScanService per request using the active DB client."""
    return ScanService(db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_ingredient_response(
    scan_ingredient: Any,
) -> ScanIngredientResponse:
    """Map a Prisma ScanIngredient record to the response schema.

    Handles the camelCase -> snake_case field name conversion and
    navigates the included Ingredient relation.

    Args:
        scan_ingredient: A Prisma ScanIngredient record with its nested
            Ingredient relation already loaded.

    Returns:
        A :class:`ScanIngredientResponse` suitable for JSON serialisation.
    """
    ingredient = scan_ingredient.ingredient
    return ScanIngredientResponse(
        ingredient_id=ingredient.id,
        inci_name=ingredient.inciName,
        common_name=ingredient.commonName,
        detected_name=scan_ingredient.detectedName,
        confidence_score=scan_ingredient.confidenceScore,
        safety_rating=ingredient.safetyRating,
        evidence_level=ingredient.evidenceLevel,
    )


def _to_scan_response(scan: PrismaScan) -> ScanResponse:
    """Map a Prisma Scan record to the response schema.

    Converts the top-level scan fields and iterates over the nested
    ``scanIngredients`` relation to build the ingredients list.

    Args:
        scan: A Prisma Scan record with its nested scanIngredients
            and ingredient relations already loaded.

    Returns:
        A :class:`ScanResponse` suitable for JSON serialisation.
    """
    scan_ingredients = getattr(scan, "scanIngredients", []) or []
    ingredients = [_to_ingredient_response(si) for si in scan_ingredients]

    return ScanResponse(
        id=scan.id,
        product_name=scan.productName,
        image_url=scan.imageUrl,
        overall_risk_score=scan.overallRiskScore,
        created_at=scan.createdAt.isoformat(),
        ingredients=ingredients,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ScanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new scan",
    description=(
        "Save a new product scan to the authenticated user's history. "
        "The scan stores the product name, optional image URL, and "
        "overall risk score. Ingredients can be added afterwards via "
        "the dedicated ingredient endpoint."
    ),
    responses={
        201: {
            "description": "Scan created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "product_name": "The Ordinary Niacinamide 10% + Zinc 1%",
                        "image_url": "https://example.com/product.jpg",
                        "overall_risk_score": 8.5,
                        "created_at": "2025-06-15T14:30:00.000Z",
                        "ingredients": [],
                    }
                }
            },
        },
        400: {
            "description": "Invalid scan data",
            "content": {
                "application/json": {
                    "example": {"detail": "Product name must not be empty"}
                }
            },
        },
        401: {
            "description": "Missing or invalid JWT",
            "content": {
                "application/json": {
                    "example": {"detail": "Could not validate credentials"}
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
async def create_scan(
    payload: ScanCreateRequest,
    current_user: User = Depends(get_current_user),
    service: ScanService = Depends(_get_scan_service),
) -> ScanResponse:
    """Create a new scan in the user's history.

    Returns **201** on success. Invalid input raises **400** via global
    DomainError handler.
    """
    scan = await service.create_scan(
        user_id=current_user.id,
        product_name=payload.product_name,
        overall_risk_score=payload.overall_risk_score,
        image_url=payload.image_url,
    )
    return _to_scan_response(scan)


@router.get(
    "",
    response_model=ScanListResponse,
    status_code=status.HTTP_200_OK,
    summary="List user scans",
    description=(
        "Return a paginated list of scans belonging to the "
        "authenticated user, ordered by creation date (newest first)."
    ),
    responses={
        200: {
            "description": "Paginated list of user scans",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                                "product_name": "The Ordinary Niacinamide 10% + Zinc 1%",
                                "image_url": "https://example.com/product.jpg",
                                "overall_risk_score": 8.5,
                                "created_at": "2025-06-15T14:30:00.000Z",
                                "ingredients": [],
                            }
                        ],
                        "total": 1,
                        "skip": 0,
                        "limit": 20,
                    }
                }
            },
        },
        401: {
            "description": "Missing or invalid JWT",
            "content": {
                "application/json": {
                    "example": {"detail": "Could not validate credentials"}
                }
            },
        },
    },
)
async def list_user_scans(
    skip: int = Query(
        default=0,
        ge=0,
        description="Number of records to skip for pagination",
        examples=[0],
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of records to return (1-100)",
        examples=[20],
    ),
    current_user: User = Depends(get_current_user),
    service: ScanService = Depends(_get_scan_service),
) -> ScanListResponse:
    """Return paginated scans for the authenticated user.

    Returns **200** with an empty list when no scans exist yet.
    """
    scans = await service.list_user_scans(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    items = [_to_scan_response(s) for s in scans]
    return ScanListResponse(
        items=items,
        total=len(items),
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{scan_id}",
    response_model=ScanResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a scan by ID",
    description=(
        "Return a single scan belonging to the authenticated user, "
        "including all detected ingredients with their full safety "
        "profiles, categories, benefits, and aliases."
    ),
    responses={
        200: {
            "description": "Scan found with full ingredient details",
            "content": {
                "application/json": {
                    "example": {
                        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "product_name": "The Ordinary Niacinamide 10% + Zinc 1%",
                        "image_url": "https://example.com/product.jpg",
                        "overall_risk_score": 8.5,
                        "created_at": "2025-06-15T14:30:00.000Z",
                        "ingredients": [
                            {
                                "ingredient_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
                                "inci_name": "Niacinamide",
                                "common_name": "Vitamin B3",
                                "detected_name": "Niacinamide",
                                "confidence_score": 0.95,
                                "safety_rating": 9.0,
                                "evidence_level": "HIGH",
                            }
                        ],
                    }
                }
            },
        },
        403: {
            "description": "User does not own this scan",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Access denied: you do not own this scan"
                    }
                }
            },
        },
        404: {
            "description": "Scan not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Scan with id 'a1b2c3d4-...' not found"}
                }
            },
        },
        401: {
            "description": "Missing or invalid JWT",
            "content": {
                "application/json": {
                    "example": {"detail": "Could not validate credentials"}
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
async def get_scan(
    scan_id: str = Path(
        ...,
        description="UUID of the scan to retrieve",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    ),
    current_user: User = Depends(get_current_user),
    service: ScanService = Depends(_get_scan_service),
) -> ScanResponse:
    """Return a single scan by ID.

    Returns **200** on success. Not found raises **404**, access denied
    raises **403**, both via global DomainError handler.
    """
    scan = await service.get_scan_by_id(
        scan_id=scan_id,
        user_id=current_user.id,
    )
    return _to_scan_response(scan)


@router.delete(
    "/{scan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a scan",
    description=(
        "Permanently remove a scan and all its associated ingredient "
        "records. Only the scan owner may perform this action."
    ),
    responses={
        204: {"description": "Scan deleted successfully"},
        403: {
            "description": "User does not own this scan",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Access denied: you do not own this scan"
                    }
                }
            },
        },
        404: {
            "description": "Scan not found",
            "content": {
                "application/json": {
                    "example": {"detail": "Scan with id 'a1b2c3d4-...' not found"}
                }
            },
        },
        401: {
            "description": "Missing or invalid JWT",
            "content": {
                "application/json": {
                    "example": {"detail": "Could not validate credentials"}
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
async def delete_scan(
    scan_id: str = Path(
        ...,
        description="UUID of the scan to delete",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    ),
    current_user: User = Depends(get_current_user),
    service: ScanService = Depends(_get_scan_service),
) -> Response:
    """Delete a scan by ID.

    Returns **204** on success. Not found raises **404**, access denied
    raises **403**, both via global DomainError handler.
    """
    await service.delete_scan(
        scan_id=scan_id,
        user_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
