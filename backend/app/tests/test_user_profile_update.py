"""
Tests for the user profile update feature (Milestone 4.1).

Covers:
    A. Schema validation — UserUpdateRequest
    B. Service layer — update_current_user
    C. Endpoint — PUT /users/me
    D. Security — protected fields, hashedPassword, unauthenticated

Run with:
    pytest app/tests/test_user_profile_update.py -v
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prisma.models import User

from app.api.users import router as users_router
from app.core.dependencies import get_current_user
from app.core.exceptions import DomainError
from app.database import get_db
from app.schemas.auth import UserUpdateRequest
from app.services.auth_service import DuplicateError, update_current_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously (project convention)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _mock_get_current_user() -> User:
    """Return a fake authenticated user (no DB required)."""
    user = MagicMock(spec=User)
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "alice@example.com"
    user.username = "alice"
    user.role = "USER"
    user.hashedPassword = "$2b$12$hashedpassword"
    return user


def _make_mock_db() -> MagicMock:
    """Create a mock Prisma DB client for endpoint tests."""

    async def _mock_update(**kwargs):
        """Return a mock user reflecting the update data."""
        data = kwargs.get("data", {})
        mock_user = MagicMock()
        mock_user.id = "00000000-0000-0000-0000-000000000001"
        mock_user.email = data.get("email", "alice@example.com")
        mock_user.username = data.get("username", "alice")
        mock_user.role = "USER"
        return mock_user

    mock_db = MagicMock()
    mock_db.user.find_unique = AsyncMock(return_value=None)
    mock_db.user.update = AsyncMock(side_effect=_mock_update)
    return mock_db


# ---------------------------------------------------------------------------
# Test app factory — minimal app for endpoint tests
# ---------------------------------------------------------------------------


def _build_test_app() -> FastAPI:
    """Create a minimal FastAPI app for testing the users router."""

    async def _domain_error_handler(request, exc: DomainError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    async def _unhandled_error_handler(request, exc: Exception):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred"},
        )

    app = FastAPI(title="DToxOut Profile Update Test")
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)

    # Override auth dependency so protected endpoints work without a DB
    app.dependency_overrides[get_current_user] = _mock_get_current_user
    # Override DB dependency so service can run without a real DB
    async def _mock_get_db():
        yield _make_mock_db()

    app.dependency_overrides[get_db] = _mock_get_db

    app.include_router(users_router)

    return app


@pytest.fixture()
def profile_client() -> TestClient:
    """Provide a test client with auth and DB dependencies overridden."""
    app = _build_test_app()
    return TestClient(app, raise_server_exceptions=False)


# ===========================================================================
# SECTION A — Schema Validation
# ===========================================================================


class TestUserUpdateRequestSchema:
    """Verify UserUpdateRequest validation rules."""

    def test_email_only_is_valid(self) -> None:
        """Providing only email is valid."""
        req = UserUpdateRequest(email="new@example.com")
        assert req.email == "new@example.com"
        assert req.username is None

    def test_username_only_is_valid(self) -> None:
        """Providing only username is valid."""
        req = UserUpdateRequest(username="newname")
        assert req.email is None
        assert req.username == "newname"

    def test_both_fields_is_valid(self) -> None:
        """Providing both email and username is valid."""
        req = UserUpdateRequest(email="new@example.com", username="newname")
        assert req.email == "new@example.com"
        assert req.username == "newname"

    def test_empty_body_rejected(self) -> None:
        """Empty body (no fields) raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserUpdateRequest()
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_blank_username_rejected(self) -> None:
        """Username shorter than 3 chars raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserUpdateRequest(username="ab")
        errors = exc_info.value.errors()
        assert any(
            e["loc"][-1] == "username" for e in errors
        )

    def test_invalid_email_rejected(self) -> None:
        """Invalid email format raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserUpdateRequest(email="not-an-email")
        errors = exc_info.value.errors()
        assert any(
            e["loc"][-1] == "email" for e in errors
        )

    def test_username_too_long_rejected(self) -> None:
        """Username longer than 30 chars raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UserUpdateRequest(username="a" * 31)
        errors = exc_info.value.errors()
        assert any(
            e["loc"][-1] == "username" for e in errors
        )

    def test_protected_fields_not_accepted(self) -> None:
        """Fields like id, hashedPassword, role are not in the schema."""
        # Pydantic v2 ignores extra fields by default
        req = UserUpdateRequest(
            email="valid@example.com",
            id="should-be-ignored",
            role="ADMIN",
            hashedPassword="should-be-ignored",
        )
        assert req.email == "valid@example.com"
        assert not hasattr(req, "id") or req.model_extra is None


# ===========================================================================
# SECTION B — Service Layer
# ===========================================================================


class TestUpdateCurrentUserService:
    """Verify update_current_user service logic with mock DB."""

    def _make_user(self, **overrides) -> MagicMock:
        """Create a mock User with default values."""
        defaults = {
            "id": "user-1",
            "email": "alice@example.com",
            "username": "alice",
            "role": "USER",
            "hashedPassword": "$2b$12$hashed",
        }
        defaults.update(overrides)
        user = MagicMock(spec=User)
        for k, v in defaults.items():
            setattr(user, k, v)
        return user

    def test_update_email_only(self) -> None:
        """Updating only email works correctly."""
        mock_db = MagicMock()
        current = self._make_user()

        updated = self._make_user(email="bob@example.com")
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=updated)

        req = UserUpdateRequest(email="bob@example.com")
        result = _run(update_current_user(mock_db, current, req))

        assert result.email == "bob@example.com"
        assert result.username == "alice"
        assert result.message == "Profile updated successfully"

    def test_update_username_only(self) -> None:
        """Updating only username works correctly."""
        mock_db = MagicMock()
        current = self._make_user()

        updated = self._make_user(username="bob")
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=updated)

        req = UserUpdateRequest(username="bob")
        result = _run(update_current_user(mock_db, current, req))

        assert result.email == "alice@example.com"
        assert result.username == "bob"

    def test_update_both_fields(self) -> None:
        """Updating both email and username works correctly."""
        mock_db = MagicMock()
        current = self._make_user()

        updated = self._make_user(email="bob@example.com", username="bob")
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=updated)

        req = UserUpdateRequest(email="bob@example.com", username="bob")
        result = _run(update_current_user(mock_db, current, req))

        assert result.email == "bob@example.com"
        assert result.username == "bob"

    def test_same_email_no_duplicate_error(self) -> None:
        """Keeping the same email does not trigger DuplicateError."""
        mock_db = MagicMock()
        current = self._make_user(email="alice@example.com")

        # find_unique should NOT be called for email since it's unchanged
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=current)

        req = UserUpdateRequest(email="alice@example.com")
        result = _run(update_current_user(mock_db, current, req))

        assert result.email == "alice@example.com"
        # find_unique for username check (username not provided, so 0 calls)
        assert mock_db.user.find_unique.call_count == 0

    def test_same_username_no_duplicate_error(self) -> None:
        """Keeping the same username does not trigger DuplicateError."""
        mock_db = MagicMock()
        current = self._make_user(username="alice")

        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=current)

        req = UserUpdateRequest(username="alice")
        result = _run(update_current_user(mock_db, current, req))

        assert result.username == "alice"
        assert mock_db.user.find_unique.call_count == 0

    def test_duplicate_email_raises_conflict(self) -> None:
        """Changing email to one already taken raises DuplicateError."""
        mock_db = MagicMock()
        current = self._make_user()

        other_user = self._make_user(
            id="user-2", email="taken@example.com"
        )
        mock_db.user.find_unique = AsyncMock(return_value=other_user)

        req = UserUpdateRequest(email="taken@example.com")
        with pytest.raises(DuplicateError) as exc_info:
            _run(update_current_user(mock_db, current, req))

        assert exc_info.value.status_code == 409
        assert "email" in exc_info.value.detail.lower()

    def test_duplicate_username_raises_conflict(self) -> None:
        """Changing username to one already taken raises DuplicateError."""
        mock_db = MagicMock()
        current = self._make_user()

        other_user = self._make_user(
            id="user-2", username="taken"
        )
        mock_db.user.find_unique = AsyncMock(return_value=other_user)

        req = UserUpdateRequest(username="taken")
        with pytest.raises(DuplicateError) as exc_info:
            _run(update_current_user(mock_db, current, req))

        assert exc_info.value.status_code == 409
        assert "username" in exc_info.value.detail.lower()

    def test_no_db_call_when_no_changes(self) -> None:
        """When same values are provided, no DB update is called."""
        mock_db = MagicMock()
        current = self._make_user()

        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock()

        req = UserUpdateRequest(
            email="alice@example.com", username="alice"
        )
        result = _run(update_current_user(mock_db, current, req))

        assert result.email == "alice@example.com"
        mock_db.user.update.assert_not_called()

    def test_response_never_exposes_hashed_password(self) -> None:
        """UserUpdateResponse does not contain hashedPassword."""
        mock_db = MagicMock()
        current = self._make_user()

        updated = self._make_user(email="bob@example.com")
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=updated)

        req = UserUpdateRequest(email="bob@example.com")
        result = _run(update_current_user(mock_db, current, req))

        result_dict = result.model_dump()
        assert "hashedPassword" not in result_dict
        assert "hashed_password" not in result_dict

    def test_role_never_changed(self) -> None:
        """update_current_user never modifies the user's role."""
        mock_db = MagicMock()
        current = self._make_user(role="USER")

        updated = self._make_user(role="USER")
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.update = AsyncMock(return_value=updated)

        req = UserUpdateRequest(email="new@example.com")
        result = _run(update_current_user(mock_db, current, req))

        assert result.role == "USER"
        # Verify update data never includes role
        call_kwargs = mock_db.user.update.call_args
        assert "role" not in call_kwargs.kwargs.get("data", {})


# ===========================================================================
# SECTION C — Endpoint (PUT /users/me)
# ===========================================================================


class TestUpdateUserProfileEndpoint:
    """Verify PUT /users/me endpoint behavior."""

    def test_update_email(self, profile_client: TestClient) -> None:
        """Authenticated user can update email."""
        response = profile_client.put(
            "/users/me",
            json={"email": "new@example.com"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["message"] == "Profile updated successfully"

    def test_update_username(self, profile_client: TestClient) -> None:
        """Authenticated user can update username."""
        response = profile_client.put(
            "/users/me",
            json={"username": "newname"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "newname"

    def test_update_both(self, profile_client: TestClient) -> None:
        """Authenticated user can update both fields."""
        response = profile_client.put(
            "/users/me",
            json={"email": "new@example.com", "username": "newname"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "new@example.com"
        assert body["username"] == "newname"

    def test_empty_body_rejected(self, profile_client: TestClient) -> None:
        """Empty update body returns 422 (validation error)."""
        response = profile_client.put("/users/me", json={})
        assert response.status_code == 422

    def test_unauthenticated_rejected(self) -> None:
        """Unauthenticated request is rejected (403 from HTTPBearer)."""
        app = _build_test_app()
        # Remove auth override to test unauthenticated path
        app.dependency_overrides.clear()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.put(
            "/users/me",
            json={"email": "new@example.com"},
        )
        assert response.status_code == 403

    def test_response_no_hashed_password(
        self, profile_client: TestClient
    ) -> None:
        """Response does not contain hashedPassword."""
        response = profile_client.put(
            "/users/me",
            json={"email": "new@example.com"},
        )
        assert response.status_code == 200
        body = response.json()
        assert "hashedPassword" not in body
        assert "hashed_password" not in body

    def test_role_not_modifiable(self, profile_client: TestClient) -> None:
        """Attempting to set role via extra body field has no effect."""
        response = profile_client.put(
            "/users/me",
            json={"email": "new@example.com", "role": "ADMIN"},
        )
        # Should succeed (role field is ignored by schema)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "USER"

    def test_response_has_correct_structure(
        self, profile_client: TestClient
    ) -> None:
        """Response contains id, email, username, role, message."""
        response = profile_client.put(
            "/users/me",
            json={"username": "newname"},
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {
            "id",
            "email",
            "username",
            "role",
            "message",
        }


# ===========================================================================
# SECTION D — Edge Cases
# ===========================================================================


class TestProfileUpdateEdgeCases:
    """Verify edge cases for profile updates."""

    def test_invalid_email_format_rejected(
        self, profile_client: TestClient
    ) -> None:
        """Invalid email format returns 422."""
        response = profile_client.put(
            "/users/me",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 422

    def test_blank_username_rejected(
        self, profile_client: TestClient
    ) -> None:
        """Blank/short username returns 422."""
        response = profile_client.put(
            "/users/me",
            json={"username": "ab"},
        )
        assert response.status_code == 422

    def test_long_username_rejected(
        self, profile_client: TestClient
    ) -> None:
        """Username > 30 chars returns 422."""
        response = profile_client.put(
            "/users/me",
            json={"username": "a" * 31},
        )
        assert response.status_code == 422

    def test_get_users_me_still_works(
        self, profile_client: TestClient
    ) -> None:
        """GET /users/me is not affected by the new PUT endpoint."""
        response = profile_client.get("/users/me")
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "00000000-0000-0000-0000-000000000001"
        assert body["email"] == "alice@example.com"
        assert body["username"] == "alice"
        assert "hashedPassword" not in body
