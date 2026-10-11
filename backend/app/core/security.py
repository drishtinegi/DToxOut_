"""
Security utilities for password hashing and JWT token management.

This module provides the core building blocks for authentication:

- ``hash_password``  — bcrypt hashing
- ``verify_password`` — bcrypt verification
- ``create_access_token``  — short-lived JWT access token
- ``create_refresh_token`` — long-lived JWT refresh token
- ``decode_token``    — decode and validate a JWT

Usage:

    from app.core.security import hash_password, verify_password

    hashed = hash_password("my-secret")
    assert verify_password("my-secret", hashed)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

# bcrypt context — uses passlib with the bcrypt backend.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt.

    Args:
        password: The raw password to hash.

    Returns:
        The bcrypt-hashed password string.
    """
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash.

    Args:
        plain_password: The raw password to check.
        hashed_password: The stored bcrypt hash.

    Returns:
        ``True`` if the password matches, ``False`` otherwise.
    """
    return _pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT exceptions
# ---------------------------------------------------------------------------


class TokenExpiredError(Exception):
    """Raised when a JWT has passed its expiration time."""


class TokenInvalidError(Exception):
    """Raised when a JWT is malformed, has an invalid signature, or is otherwise invalid."""


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _create_token(
    data: dict[str, Any],
    expires_delta: timedelta,
) -> str:
    """Create a signed JWT with an expiration claim.

    Args:
        data: Claims to encode into the token (must include ``sub``).
        expires_delta: How long until the token expires.

    Returns:
        The encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_access_token(
    subject: str,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a short-lived access token.

    Args:
        subject: The unique identifier for the token bearer (e.g. user ID).
        extra_claims: Optional additional claims to embed.

    Returns:
        A signed JWT access token string.
    """
    claims: dict[str, Any] = {"sub": subject, "type": "access"}
    if extra_claims:
        claims.update(extra_claims)
    return _create_token(
        claims,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    subject: str,
    extra_claims: Optional[dict[str, Any]] = None,
) -> str:
    """Create a long-lived refresh token.

    Args:
        subject: The unique identifier for the token bearer (e.g. user ID).
        extra_claims: Optional additional claims to embed.

    Returns:
        A signed JWT refresh token string.
    """
    claims: dict[str, Any] = {"sub": subject, "type": "refresh"}
    if extra_claims:
        claims.update(extra_claims)
    return _create_token(
        claims,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Args:
        token: The JWT string to decode.

    Returns:
        The decoded payload dictionary.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is malformed, has an invalid
            signature, or is otherwise invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError:
        raise TokenInvalidError("Invalid token")
