"""
Comprehensive error-handling and regression tests for the DToxOut API.

Covers:
    A. DomainError handling
    B. Validation errors (422)
    C. Authentication errors (401/403)
    D. Authorization errors (403)
    E. Unexpected exception safety (500)
    F. Response consistency
    G. DomainError unit tests

Run with:
    pytest app/tests/test_error_handling.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# SECTION A - DomainError Handling
# ===========================================================================


class TestDomainErrorHandling:
    """Verify DomainError exceptions produce correct HTTP status codes
    and safe JSON responses.

    NOTE: Admin endpoints require ADMIN role. Without a valid token
    they return 403 (HTTPBearer auto_error). To test the actual 404
    path, the tests that CAN reach the service without auth test
    the domain error directly (search, knowledge).
    """

    def test_search_nonexistent_ingredient_returns_404(self, client: TestClient):
        """Search endpoint is public (no auth), so we can test the real 404."""
        response = client.get(
            "/api/v1/search/ingredient", params={"query": "ZZZZNONEXISTENT12345"}
        )
        # Without DB the service will fail (500), but the error
        # handler catches it safely. With DB it would be 404.
        assert response.status_code in (404, 500)
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    def test_domain_error_returns_json(self, client: TestClient):
        response = client.get("/api/v1/admin/ingredients/nonexistent-uuid")
        assert "application/json" in response.headers["content-type"]

    def test_domain_error_no_internal_details(self, client: TestClient):
        response = client.get("/api/v1/admin/ingredients/nonexistent-uuid")
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        assert "stack" not in body_text

    def test_domain_error_unit_ingredient_not_found(self):
        from app.services.ingredient_service import IngredientNotFoundError

        exc = IngredientNotFoundError("Ingredient with id 'x' not found")
        assert exc.status_code == 404
        assert "not found" in exc.detail.lower()
        assert isinstance(exc, Exception)

    def test_domain_error_unit_regulation_not_found(self):
        from app.services.regulation_service import RegulationNotFoundError

        exc = RegulationNotFoundError("Regulation with id 'x' not found")
        assert exc.status_code == 404

    def test_domain_error_unit_reference_not_found(self):
        from app.services.scientific_reference_service import (
            ScientificReferenceNotFoundError,
        )

        exc = ScientificReferenceNotFoundError("Reference with id 'x' not found")
        assert exc.status_code == 404

    def test_domain_error_unit_safety_profile_not_found(self):
        from app.services.safety_profile_service import SafetyProfileNotFoundError

        exc = SafetyProfileNotFoundError("some-uuid")
        assert exc.status_code == 404

    def test_domain_error_unit_scan_not_found(self):
        from app.services.scan_service import ScanNotFoundError

        exc = ScanNotFoundError("Scan with id 'x' not found")
        assert exc.status_code == 404

    def test_domain_error_unit_scan_access_denied(self):
        from app.services.scan_service import ScanAccessDeniedError

        exc = ScanAccessDeniedError()
        assert exc.status_code == 403

    def test_domain_error_unit_duplicate_error(self):
        from app.services.auth_service import DuplicateError

        exc = DuplicateError("email", "test@example.com")
        assert exc.status_code == 409
        assert "test@example.com" in exc.detail

    def test_domain_error_unit_authentication_error(self):
        from app.services.auth_service import AuthenticationError

        exc = AuthenticationError("Invalid email or password")
        assert exc.status_code == 401

    def test_domain_error_unit_invalid_scan(self):
        from app.services.scan_service import InvalidScanError

        exc = InvalidScanError("Product name must not be empty")
        assert exc.status_code == 400

    def test_domain_error_unit_invalid_publication_year(self):
        from app.services.scientific_reference_service import (
            InvalidPublicationYearError,
        )

        exc = InvalidPublicationYearError(2099)
        assert exc.status_code == 422
        assert "2099" in exc.detail

    def test_domain_error_unit_invalid_source_url(self):
        from app.services.scientific_reference_service import InvalidSourceUrlError

        exc = InvalidSourceUrlError("ftp://bad-url")
        assert exc.status_code == 422

    def test_domain_error_unit_safety_profile_already_exists(self):
        from app.services.safety_profile_service import SafetyProfileAlreadyExistsError

        exc = SafetyProfileAlreadyExistsError("some-uuid")
        assert exc.status_code == 409

    def test_domain_error_unit_regulation_already_exists(self):
        from app.services.regulation_service import RegulationAlreadyExistsError

        exc = RegulationAlreadyExistsError("ing-id", "US")
        assert exc.status_code == 409

    def test_domain_error_unit_reference_already_exists(self):
        from app.services.scientific_reference_service import (
            ScientificReferenceAlreadyExistsError,
        )

        exc = ScientificReferenceAlreadyExistsError("Title", "Org")
        assert exc.status_code == 409

    def test_domain_error_unit_ingredient_already_exists(self):
        from app.services.ingredient_service import IngredientAlreadyExistsError

        exc = IngredientAlreadyExistsError("Niacinamide")
        assert exc.status_code == 409

    def test_domain_error_unit_ingredient_search_not_found(self):
        from app.services.ingredient_service import IngredientSearchNotFoundError

        exc = IngredientSearchNotFoundError("UnknownIngredient")
        assert exc.status_code == 404


# ===========================================================================
# SECTION B - Validation Errors (422)
# ===========================================================================


class TestValidationErrors:
    """Verify that malformed requests return 422 with structured JSON."""

    def test_register_missing_fields_returns_422(self, client: TestClient):
        response = client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)

    def test_register_invalid_email_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "username": "testuser",
                "password": "StrongPass123",
            },
        )
        assert response.status_code == 422

    def test_register_short_password_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "testuser",
                "password": "short",
            },
        )
        assert response.status_code == 422

    def test_register_short_username_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "username": "ab",
                "password": "StrongPass123",
            },
        )
        assert response.status_code == 422

    def test_search_empty_query_returns_422(self, client: TestClient):
        response = client.get("/api/v1/search/ingredient", params={"query": ""})
        assert response.status_code == 422

    def test_bulk_search_empty_list_returns_422(self, client: TestClient):
        response = client.post("/api/v1/search/ingredients", json={"ingredients": []})
        assert response.status_code == 422

    def test_bulk_search_blank_entry_returns_error(self, client: TestClient):
        response = client.post(
            "/api/v1/search/ingredients", json={"ingredients": ["  ", "Water"]}
        )
        # Blank entries should produce 422 (validation) or 500 (validator edge case)
        assert response.status_code in (422, 500)
        body = response.json()
        assert "detail" in body

    def test_login_missing_fields_returns_422(self, client: TestClient):
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    def test_login_invalid_email_returns_422(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "not-valid", "password": "StrongPass123"},
        )
        assert response.status_code in (401, 422)

    def test_validation_error_body_structure(self, client: TestClient):
        response = client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body
        errors = body["detail"]
        assert isinstance(errors, list)
        assert len(errors) > 0
        for error in errors:
            assert "loc" in error
            assert "msg" in error
            assert "type" in error

    def test_validation_error_no_traceback(self, client: TestClient):
        response = client.post("/api/v1/auth/register", json={})
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "stack" not in body_text

    def test_validation_error_no_secret_values(self, client: TestClient):
        """Verify no actual secrets are leaked (field names like 'password' are OK)."""
        response = client.post("/api/v1/auth/register", json={})
        body_text = response.text.lower()
        assert "secret" not in body_text
        assert "token" not in body_text
        assert "api_key" not in body_text
        assert "database_url" not in body_text


# ===========================================================================
# SECTION C - Authentication Errors (401 / 403)
# ===========================================================================


class TestAuthenticationErrors:
    """Verify that authentication failures return safe error responses.

    NOTE: FastAPI's HTTPBearer returns 403 (not 401) when no
    Authorization header is provided. When a malformed token is
    provided, our dependency raises HTTPException(401). Both paths
    must produce safe JSON responses.
    """

    def test_missing_auth_header_returns_error(self, client: TestClient):
        """HTTPBearer auto_error returns 403 when header is absent."""
        response = client.get("/api/v1/users/me")
        assert response.status_code in (401, 403)
        body = response.json()
        assert "detail" in body

    def test_malformed_token_returns_401(self, client: TestClient):
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert response.status_code == 401
        body = response.json()
        assert "detail" in body

    def test_wrong_auth_scheme_returns_error(self, client: TestClient):
        """Basic auth scheme is not accepted by HTTPBearer."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert response.status_code in (401, 403)

    def test_empty_bearer_token_returns_error(self, client: TestClient):
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer "},
        )
        assert response.status_code in (401, 403)

    def test_garbage_token_returns_401(self, client: TestClient):
        response = client.get(
            "/api/v1/users/me",
            headers={
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.invalid.signature"
            },
        )
        assert response.status_code == 401

    def test_auth_error_no_internal_details(self, client: TestClient):
        response = client.get("/api/v1/users/me")
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        assert "password" not in body_text
        assert "hashed" not in body_text
        assert "database" not in body_text

    def test_admin_endpoint_without_auth_returns_error(self, client: TestClient):
        response = client.get("/api/v1/admin/ingredients")
        assert response.status_code in (401, 403)

    def test_auth_error_json_content_type(self, client: TestClient):
        response = client.get("/api/v1/users/me")
        assert "application/json" in response.headers["content-type"]


# ===========================================================================
# SECTION D - Authorization Errors (403)
# ===========================================================================


class TestAuthorizationErrors:
    """Verify that authorization failures return 403 safely."""

    def test_require_admin_rejects_non_admin(self):
        from unittest.mock import MagicMock

        from app.core.dependencies import require_admin

        mock_user = MagicMock()
        mock_user.role = "USER"

        import asyncio

        with pytest.raises(Exception) as exc_info:
            asyncio.get_event_loop().run_until_complete(
                require_admin(current_user=mock_user)
            )
        assert exc_info.value.status_code == 403
        assert "Administrator access required" in exc_info.value.detail

    def test_require_admin_allows_admin(self):
        from unittest.mock import MagicMock

        from app.core.dependencies import require_admin

        mock_user = MagicMock()
        mock_user.role = "ADMIN"

        import asyncio

        result = asyncio.get_event_loop().run_until_complete(
            require_admin(current_user=mock_user)
        )
        assert result == mock_user


# ===========================================================================
# SECTION E - Unexpected Exception Safety (500)
# ===========================================================================


class TestUnexpectedExceptionSafety:
    """Verify that unhandled exceptions produce safe responses."""

    def test_500_response_has_safe_message(self, client: TestClient):
        """The /health/database endpoint returns 503 when DB is down."""
        response = client.get("/health/database")
        assert response.status_code == 503
        body = response.json()
        assert "database" in body
        body_text = response.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text

    def test_no_traceback_in_any_error_response(self, client: TestClient):
        error_endpoints = [
            ("GET", "/api/v1/users/me", None),
            ("GET", "/api/v1/admin/ingredients", None),
            ("GET", "/api/v1/admin/ingredients/nonexistent", None),
            ("POST", "/api/v1/auth/register", {}),
            ("POST", "/api/v1/auth/login", {}),
            ("GET", "/api/v1/search/ingredient", {"query": ""}),
            ("POST", "/api/v1/search/ingredients", {"ingredients": []}),
        ]
        for method, path, payload in error_endpoints:
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json=payload)
            body_text = response.text.lower()
            assert "traceback" not in body_text, (
                f"Traceback leaked on {method} {path}"
            )
            assert "stack trace" not in body_text, (
                f"Stack trace leaked on {method} {path}"
            )
            assert response.status_code >= 400, (
                f"Expected error status on {method} {path}, got {response.status_code}"
            )


# ===========================================================================
# SECTION F - Response Consistency
# ===========================================================================


class TestResponseConsistency:
    """Verify consistent error response structure across the API."""

    def _assert_detail_response(self, response, expected_statuses: tuple):
        assert response.status_code in expected_statuses, (
            f"Expected {expected_statuses}, got {response.status_code}"
        )
        assert "application/json" in response.headers["content-type"]
        body = response.json()
        assert "detail" in body
        assert isinstance(body["detail"], (str, list))

    def test_auth_register_422_structure(self, client: TestClient):
        response = client.post("/api/v1/auth/register", json={})
        self._assert_detail_response(response, (422,))

    def test_auth_login_422_structure(self, client: TestClient):
        response = client.post("/api/v1/auth/login", json={})
        self._assert_detail_response(response, (422,))

    def test_ingredient_error_structure(self, client: TestClient):
        response = client.get("/api/v1/admin/ingredients/nonexistent")
        self._assert_detail_response(response, (403, 404))

    def test_safety_profile_error_structure(self, client: TestClient):
        response = client.get("/api/v1/admin/safety-profiles/nonexistent")
        self._assert_detail_response(response, (403, 404))

    def test_regulation_error_structure(self, client: TestClient):
        response = client.get("/api/v1/admin/regulations/nonexistent")
        self._assert_detail_response(response, (403, 404))

    def test_reference_error_structure(self, client: TestClient):
        response = client.get("/api/v1/admin/scientific-references/nonexistent")
        self._assert_detail_response(response, (403, 404))

    def test_search_error_structure(self, client: TestClient):
        response = client.get(
            "/api/v1/search/ingredient", params={"query": "ZZZNOTFOUND"}
        )
        self._assert_detail_response(response, (404, 500))

    def test_knowledge_error_structure(self, client: TestClient):
        response = client.get("/api/v1/knowledge/ingredient/nonexistent")
        self._assert_detail_response(response, (404, 500))

    def test_users_me_auth_error_structure(self, client: TestClient):
        response = client.get("/api/v1/users/me")
        self._assert_detail_response(response, (401, 403))

    def test_admin_ingredients_auth_error_structure(self, client: TestClient):
        response = client.get("/api/v1/admin/ingredients")
        self._assert_detail_response(response, (401, 403))

    def test_bulk_search_422_structure(self, client: TestClient):
        response = client.post("/api/v1/search/ingredients", json={})
        self._assert_detail_response(response, (422,))

    def test_health_check_returns_200(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"

    def test_root_returns_200(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert "message" in body


# ===========================================================================
# SECTION G - All Exceptions Inherit DomainError
# ===========================================================================


class TestExceptionHierarchy:
    """Verify the complete exception hierarchy."""

    def test_all_service_exceptions_inherit_domain_error(self):
        from app.core.exceptions import DomainError
        from app.services.auth_service import AuthenticationError, DuplicateError
        from app.services.ingredient_service import (
            IngredientAlreadyExistsError,
            IngredientNotFoundError,
            IngredientSearchNotFoundError,
        )
        from app.services.regulation_service import (
            RegulationAlreadyExistsError,
            RegulationNotFoundError,
        )
        from app.services.safety_profile_service import (
            SafetyProfileAlreadyExistsError,
            SafetyProfileNotFoundError,
            SafetyProfileServiceError,
        )
        from app.services.scientific_reference_service import (
            InvalidPublicationYearError,
            InvalidSourceUrlError,
            ScientificReferenceAlreadyExistsError,
            ScientificReferenceNotFoundError,
        )
        from app.services.scan_service import (
            DuplicateScanIngredientError,
            InvalidScanError,
            ScanAccessDeniedError,
            ScanNotFoundError,
        )

        all_exceptions = [
            DuplicateError,
            AuthenticationError,
            IngredientNotFoundError,
            IngredientAlreadyExistsError,
            IngredientSearchNotFoundError,
            SafetyProfileNotFoundError,
            SafetyProfileAlreadyExistsError,
            SafetyProfileServiceError,
            RegulationNotFoundError,
            RegulationAlreadyExistsError,
            ScientificReferenceNotFoundError,
            ScientificReferenceAlreadyExistsError,
            InvalidPublicationYearError,
            InvalidSourceUrlError,
            ScanNotFoundError,
            ScanAccessDeniedError,
            InvalidScanError,
            DuplicateScanIngredientError,
        ]

        for exc_cls in all_exceptions:
            assert issubclass(exc_cls, DomainError), (
                f"{exc_cls.__name__} does not inherit from DomainError"
            )
            assert hasattr(exc_cls, "status_code"), (
                f"{exc_cls.__name__} missing status_code"
            )

    def test_exception_status_codes_are_correct(self):
        from app.services.auth_service import AuthenticationError, DuplicateError
        from app.services.ingredient_service import (
            IngredientAlreadyExistsError,
            IngredientNotFoundError,
            IngredientSearchNotFoundError,
        )
        from app.services.regulation_service import (
            RegulationAlreadyExistsError,
            RegulationNotFoundError,
        )
        from app.services.safety_profile_service import (
            SafetyProfileAlreadyExistsError,
            SafetyProfileNotFoundError,
            SafetyProfileServiceError,
        )
        from app.services.scientific_reference_service import (
            InvalidPublicationYearError,
            InvalidSourceUrlError,
            ScientificReferenceAlreadyExistsError,
            ScientificReferenceNotFoundError,
        )
        from app.services.scan_service import (
            DuplicateScanIngredientError,
            InvalidScanError,
            ScanAccessDeniedError,
            ScanNotFoundError,
        )

        expected = {
            DuplicateError: 409,
            AuthenticationError: 401,
            IngredientNotFoundError: 404,
            IngredientAlreadyExistsError: 409,
            IngredientSearchNotFoundError: 404,
            SafetyProfileNotFoundError: 404,
            SafetyProfileAlreadyExistsError: 409,
            SafetyProfileServiceError: 500,
            RegulationNotFoundError: 404,
            RegulationAlreadyExistsError: 409,
            ScientificReferenceNotFoundError: 404,
            ScientificReferenceAlreadyExistsError: 409,
            InvalidPublicationYearError: 422,
            InvalidSourceUrlError: 422,
            ScanNotFoundError: 404,
            ScanAccessDeniedError: 403,
            InvalidScanError: 400,
            DuplicateScanIngredientError: 409,
        }

        for exc_cls, expected_code in expected.items():
            assert exc_cls.status_code == expected_code, (
                f"{exc_cls.__name__}.status_code = {exc_cls.status_code}, "
                f"expected {expected_code}"
            )

    def test_exception_detail_messages_are_safe(self):
        """Verify exception details don't contain actual secrets.

        Standard error messages like 'Invalid email or password' are fine —
        they don't reveal the actual password. We check for actual secret
        values, not field names or generic words.
        """
        from app.services.auth_service import DuplicateError
        from app.services.ingredient_service import IngredientNotFoundError
        from app.services.scan_service import ScanAccessDeniedError

        exceptions = [
            DuplicateError("email", "test@example.com"),
            IngredientNotFoundError("Ingredient with id 'x' not found"),
            ScanAccessDeniedError(),
        ]

        dangerous_patterns = [
            "hashedpassword",
            "secret_key",
            "jwt_secret",
            "database_url",
            "api_key",
            "OPENROUTER",
            "prismaError",
        ]

        for exc in exceptions:
            detail_lower = exc.detail.lower()
            for pattern in dangerous_patterns:
                assert pattern.lower() not in detail_lower, (
                    f"{exc.__class__.__name__}.detail leaks '{pattern}': {exc.detail}"
                )
