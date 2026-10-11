"""
Authentication API routes.

Currently exposes registration, login, token refresh, and a protected
profile endpoint. Logout will be added in later milestones.
"""

from fastapi import APIRouter, Depends, Request, Response, status
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import get_current_user
from app.database import get_db
from app.middleware.rate_limiting import limiter
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegistrationRequest,
    RegistrationResponse,
    UserProfile,
)
from app.services.auth_service import (
  login_user, 
  refresh_access_token, 
  register_user
)
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(
    request: Request,
    response: Response,
    payload: RegistrationRequest,
    db: Prisma = Depends(get_db),
) -> RegistrationResponse:
    """Register a new user account.

    Returns **201** on success. Duplicate email/username raises
    **409** via global DomainError handler.
    """
    return await register_user(db, payload)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Prisma = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user and return JWT tokens.

    Returns **200** with access and refresh tokens on success.
    Invalid credentials raises **401** via global DomainError handler.
    """
    return await login_user(db, payload)


@router.post(
    "/refresh",
    response_model=RefreshTokenResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest,
    db: Prisma = Depends(get_db),
) -> RefreshTokenResponse:
    """Refresh an access token using a valid refresh token.

    Returns **200** with new access and refresh tokens on success.
    Invalid or expired refresh token raises **401** via global DomainError handler.
    """
    return await refresh_access_token(db, payload)


@router.get(
    "/me",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
)
async def me(
    current_user: User = Depends(get_current_user),
) -> UserProfile:
    """Return the authenticated user's safe profile information.

    Requires a valid access token in the ``Authorization: Bearer <token>``
    header. Returns **200** with user profile on success.
    Missing, invalid, or expired token raises **401**.
    """
    role_str = (
        current_user.role.value
        if hasattr(current_user.role, "value")
        else str(current_user.role)
    )
    created_at_str = (
        current_user.createdAt.isoformat()
        if hasattr(current_user.createdAt, "isoformat")
        else str(current_user.createdAt)
    )
    return UserProfile(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        role=role_str,
        createdAt=created_at_str,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout() -> dict[str, str]:
    """Client logout and session token cleanup endpoint."""
    return {"message": "Logged out successfully."}

