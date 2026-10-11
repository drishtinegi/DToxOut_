"""
Authentication business logic.

Contains registration, login, token refresh, and profile-update workflows.
All database interaction stays here — route handlers must NOT call Prisma
directly for auth operations.
"""

from prisma import Prisma
from prisma.models import User

from app.core.exceptions import DomainError
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    RegistrationRequest,
    RegistrationResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class DuplicateError(DomainError):
    """Raised when a uniqueness constraint is violated."""

    status_code = 409

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        self.value = value
        super().__init__(f"{field} '{value}' is already taken")


class AuthenticationError(DomainError):
    """Raised when login credentials are invalid."""

    status_code = 401

    def __init__(self, detail: str = "Invalid email or password") -> None:
        super().__init__(detail)


class InvalidTokenError(DomainError):
    """Raised when a JWT is invalid, expired, or not the expected type."""

    status_code = 401

    def __init__(self, detail: str = "Invalid or expired token") -> None:
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


async def register_user(
    db: Prisma,
    payload: RegistrationRequest,
) -> RegistrationResponse:
    """Register a new user.

    Steps:
        1. Check for an existing email — raise ``DuplicateError`` if found.
        2. Check for an existing username — raise ``DuplicateError`` if found.
        3. Hash the plaintext password.
        4. Insert the new user row via Prisma.

    Args:
        db: Active Prisma database client.
        payload: Validated registration request body.

    Returns:
        A ``RegistrationResponse`` with the new user's id and details.

    Raises:
        DuplicateError: If the email or username already exists.
    """

    # ---- 1. Duplicate email check ----
    existing_email = await db.user.find_unique(where={"email": payload.email})
    if existing_email:
        raise DuplicateError("email", payload.email)

    # ---- 2. Duplicate username check ----
    existing_username = await db.user.find_unique(
        where={"username": payload.username}
    )
    if existing_username:
        raise DuplicateError("username", payload.username)

    # ---- 3. Hash password ----
    hashed = hash_password(payload.password)

    # ---- 4. Create user ----
    user = await db.user.create(
        data={
            "email": payload.email,
            "username": payload.username,
            "hashedPassword": hashed,
        }
    )

    return RegistrationResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        message="User registered successfully",
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


async def login_user(
    db: Prisma,
    payload: LoginRequest,
) -> LoginResponse:
    """Authenticate a user and issue JWT tokens.

    Steps:
        1. Look up the user by email.
        2. Verify the plaintext password against the stored hash.
        3. Generate an access token and a refresh token.
        4. Return both tokens.

    Args:
        db: Active Prisma database client.
        payload: Validated login request body.

    Returns:
        A ``LoginResponse`` containing both JWT tokens.

    Raises:
        AuthenticationError: If the email is not found or the password
            does not match.
    """

    # ---- 1. Find user by email or username ----
    identifier = payload.email.strip()
    user = await db.user.find_unique(where={"email": identifier})
    if user is None:
        user = await db.user.find_unique(where={"username": identifier})
    if user is None:
        raise AuthenticationError("Invalid email or password")

    # ---- 2. Verify password ----
    if not verify_password(payload.password, user.hashedPassword):
        raise AuthenticationError("Invalid email or password")

    # ---- 3. Generate tokens ----
    access_token = create_access_token(subject=user.id)
    refresh_token = create_refresh_token(subject=user.id)

    # ---- 4. Return tokens ----
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------


async def refresh_access_token(
    db: Prisma,
    payload: RefreshTokenRequest,
) -> RefreshTokenResponse:
    """Issue new tokens using a valid refresh token.

    Steps:
        1. Decode and validate the refresh token JWT.
        2. Verify the token type claim is ``"refresh"``.
        3. Verify the user still exists in the database.
        4. Generate a new access token and a new refresh token.
        5. Return both new tokens.

    Args:
        db: Active Prisma database client.
        payload: Validated refresh-token request body.

    Returns:
        A ``RefreshTokenResponse`` containing new JWT tokens.

    Raises:
        InvalidTokenError: If the token is expired, malformed,
            has an invalid signature, is not a refresh token,
            or the associated user no longer exists.
    """

    # ---- 1. Decode and validate ----
    try:
        payload_data = decode_token(payload.refresh_token)
    except TokenExpiredError:
        raise InvalidTokenError("Refresh token has expired")
    except TokenInvalidError:
        raise InvalidTokenError("Invalid refresh token")

    # ---- 2. Verify token type ----
    if payload_data.get("type") != "refresh":
        raise InvalidTokenError("Token is not a refresh token")

    # ---- 3. Extract subject ----
    subject = payload_data.get("sub")
    if not subject:
        raise InvalidTokenError("Invalid refresh token")

    # ---- 4. Verify user still exists ----
    user = await db.user.find_unique(where={"id": subject})
    if user is None:
        raise InvalidTokenError("User no longer exists")

    # ---- 5. Generate new tokens ----
    new_access_token = create_access_token(subject=subject)
    new_refresh_token = create_refresh_token(subject=subject)

    # ---- 6. Return new tokens ----
    return RefreshTokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


# ---------------------------------------------------------------------------
# Profile Update
# ---------------------------------------------------------------------------


async def update_current_user(
    db: Prisma,
    current_user: User,
    payload: UserUpdateRequest,
) -> UserUpdateResponse:
    """Update the authenticated user's profile (email and/or username).

    Only fields explicitly provided in the payload are updated.
    Uniqueness checks exclude the current user's own record so that
    keeping the same email/username does not trigger a false conflict.

    Args:
        db: Active Prisma database client.
        current_user: The authenticated user object from the dependency.
        payload: Validated profile-update request body.

    Returns:
        A ``UserUpdateResponse`` with the updated user details.

    Raises:
        DuplicateError: If the new email or username is already taken
            by another user.
    """
    update_data: dict[str, str] = {}

    # ---- 1. Email uniqueness check ----
    if payload.email is not None and payload.email != current_user.email:
        existing_email = await db.user.find_unique(
            where={"email": payload.email}
        )
        if existing_email is not None:
            raise DuplicateError("email", payload.email)
        update_data["email"] = payload.email

    # ---- 2. Username uniqueness check ----
    if (
        payload.username is not None
        and payload.username != current_user.username
    ):
        existing_username = await db.user.find_unique(
            where={"username": payload.username}
        )
        if existing_username is not None:
            raise DuplicateError("username", payload.username)
        update_data["username"] = payload.username

    # ---- 3. Apply updates if any fields changed ----
    if update_data:
        user = await db.user.update(
            where={"id": current_user.id},
            data=update_data,
        )
    else:
        user = current_user

    return UserUpdateResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        role=user.role,
        message="Profile updated successfully",
    )
