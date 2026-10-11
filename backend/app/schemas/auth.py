"""
Pydantic schemas for authentication endpoints.

RegistrationRequest / RegistrationResponse — POST /auth/register
LoginRequest / LoginResponse             — POST /auth/login
RefreshTokenRequest / RefreshTokenResponse — POST /auth/refresh
"""

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegistrationRequest(BaseModel):
    """Schema for the user registration request body."""

    email: EmailStr = Field(
        ...,
        description="Valid email address",
        examples=["user@example.com"],
    )
    username: str = Field(
        ...,
        min_length=3,
        max_length=30,
        description="Unique username (3-30 characters)",
        examples=["johndoe"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
        examples=["StrongP@ss1"],
    )


class RegistrationResponse(BaseModel):
    """Schema returned after a successful registration."""

    id: str = Field(..., description="UUID of the newly created user")
    email: str = Field(..., description="Registered email address")
    username: str = Field(..., description="Registered username")
    message: str = Field(..., description="Human-readable status message")


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Schema for the user login request body."""

    email: str = Field(
        ...,
        min_length=1,
        description="Registered email address or username",
        examples=["user@example.com", "johndoe"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Account password",
        examples=["StrongP@ss1"],
    )



class LoginResponse(BaseModel):
    """Schema returned after a successful login."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(
        default="bearer",
        description="Token type, always 'bearer'",
    )


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------


class RefreshTokenRequest(BaseModel):
    """Schema for the token refresh request body."""

    refresh_token: str = Field(
        ...,
        min_length=1,
        description="A valid JWT refresh token",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )


class RefreshTokenResponse(BaseModel):
    """Schema returned after a successful token refresh."""

    access_token: str = Field(..., description="Newly generated JWT access token")
    refresh_token: str = Field(..., description="Newly generated JWT refresh token")
    token_type: str = Field(
        default="bearer",
        description="Token type, always 'bearer'",
    )


# ---------------------------------------------------------------------------
# Profile Update
# ---------------------------------------------------------------------------


class UserUpdateRequest(BaseModel):
    """Schema for the authenticated user's profile update request body.

    At least one field must be provided.  Fields that are ``None`` are
    not updated.  ``id``, ``hashedPassword``, and ``role`` are never
    accepted.
    """

    email: EmailStr | None = Field(
        default=None,
        description="New email address",
        examples=["newemail@example.com"],
    )
    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=30,
        description="New username (3-30 characters)",
        examples=["newusername"],
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdateRequest":
        """Ensure at least one updatable field is provided."""
        if self.email is None and self.username is None:
            raise ValueError(
                "At least one of 'email' or 'username' must be provided"
            )
        return self


class UserUpdateResponse(BaseModel):
    """Schema returned after a successful profile update."""

    id: str = Field(..., description="UUID of the user")
    email: str = Field(..., description="Updated email address")
    username: str = Field(..., description="Updated username")
    role: str = Field(..., description="User role (unchanged)")
    message: str = Field(..., description="Human-readable status message")


# ---------------------------------------------------------------------------
# User Profile (for protected /auth/me)
# ---------------------------------------------------------------------------


class UserProfile(BaseModel):
    """Safe user profile returned by the protected /auth/me endpoint.

    Only includes non-sensitive fields — never exposes password hashes,
    refresh tokens, or internal database metadata.
    """

    id: str = Field(..., description="UUID of the user")
    email: str = Field(..., description="User email address")
    username: str = Field(..., description="User username")
    role: str = Field(..., description="User role")
    createdAt: str = Field(..., description="Account creation timestamp")
