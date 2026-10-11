"""
FastAPI dependency injection helpers.

Contains the authentication and authorization dependencies:

- ``get_current_user`` — extract and validate the JWT, load the User.
- ``require_admin``    — wraps ``get_current_user`` and enforces the
  ADMIN role, raising 403 for non-admin users.

Usage in any router:

    from fastapi import Depends
    from prisma.models import User

    from app.core.dependencies import get_current_user, require_admin
    from app.database import get_db

    @router.get("/secret")
    async def secret(user: User = Depends(get_current_user)):
        ...

    @router.get("/admin-only")
    async def admin_only(user: User = Depends(require_admin)):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prisma import Prisma
from prisma.models import User

from app.core.security import TokenExpiredError, TokenInvalidError, decode_token
from app.database import get_db

# HTTPBearer expects a standard ``Authorization: Bearer <token>`` header
# and returns the credentials object (or raises 403 if missing).
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Prisma = Depends(get_db),
) -> User:
    """Extract the authenticated user from the Authorization header.

    Flow:
        1. FastAPI extracts the Bearer token via ``HTTPBearer``.
        2. The token string is decoded and validated (expiration, signature).
        3. The ``sub`` claim (user ID) is used to fetch the User row.
        4. The User object is returned to the route handler.

    Raises:
        HTTPException 401: If the token is expired, missing, malformed,
            or the referenced user no longer exists.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    expired_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token has expired",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # ---- 1. Extract token string from credentials ----
    token = credentials.credentials

    # ---- 2. Decode the JWT ----
    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise expired_exception
    except TokenInvalidError:
        raise credentials_exception

    # ---- 3. Verify token type is "access" ----
    if payload.get("type") != "access":
        raise credentials_exception

    # ---- 4. Extract subject (user ID) ----
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    # ---- 5. Fetch the user from the database ----
    user = await db.user.find_unique(where={"id": user_id})
    if user is None:
        raise credentials_exception

    return user


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Authorization dependency that enforces the ADMIN role.

    Wraps ``get_current_user`` — the user is already authenticated.
    If the user's role is not ADMIN, a 403 is raised immediately.

    Args:
        current_user: The authenticated user injected by ``get_current_user``.

    Returns:
        The authenticated User object if role == ADMIN.

    Raises:
        HTTPException 403: If the user's role is not ADMIN.
    """
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )

    return current_user
