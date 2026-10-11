"""
User-related API routes.

Currently exposes two authenticated endpoints:

- ``GET  /users/me`` — return the profile of the currently logged-in user.
- ``PUT  /users/me`` — update the authenticated user's own profile.
"""

from fastapi import APIRouter, Depends, status
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import get_current_user
from app.database import get_db
from app.schemas.auth import UserUpdateRequest, UserUpdateResponse
from app.services.auth_service import update_current_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return the authenticated user's profile.

    Requires a valid Bearer token in the Authorization header.
    Never exposes the hashed password.
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "role": current_user.role,
    }


@router.put(
    "/me",
    response_model=UserUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def update_user_profile(
    payload: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Prisma = Depends(get_db),
) -> UserUpdateResponse:
    """Update the authenticated user's email and/or username.

    Requires a valid Bearer token.  Only fields present in the request
    body are updated.  Duplicate email/username raises **409** via the
    global ``DomainError`` handler.
    """
    return await update_current_user(db, current_user, payload)
