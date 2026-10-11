"""
API Versioning tests for DToxOut Backend (Milestone 12 Step 4).

Verifies:
    A. Versioned routes exist and respond
    B. Health endpoints remain unversioned
    C. Authentication through versioned path
    D. Protected routes enforce auth through versioned path
    E. Backward compatibility — unversioned paths still work
    F. API version metadata
    G. Route structure integrity

Run with:
    pytest app/tests/test_api_versioning.py -v
"""

from __future__ import annotations

from fastapi.testclient import TestClient


# ===========================================================================
# SECTION A — Versioned Routes Exist and Respond
# ===========================================================================


class TestVersionedRoutesExist:
    """Verify that key API routes are accessible under /api/v1/."""

    def test_auth_register_versioned(self, client: TestClient) -> None:
        """POST /api/v1/auth/register accepts requests (422 = validation works)."""
        response = client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422

    def test_auth_login_versioned(self, client: TestClient) -> None:
        """POST /api/v1/auth/login accepts requests."""
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422

    def test_users_me_versioned(self, client: TestClient) -> None:
        """GET /api/v1/users/me requires auth (403 without token)."""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 403

    def test_admin_ingredients_versioned(self, client: TestClient) -> None:
        """GET /api/v1/admin/ingredients requires admin auth."""
        response = client.get("/api/v1/admin/ingredients")
        assert response.status_code == 403

    def test_scan_analyze_versioned(self, client: TestClient) -> None:
        """POST /api/v1/scan/analyze requires auth."""
        response = client.post(
            "/api/v1/scan/analyze",
            json={"ingredients": []},
        )
        assert response.status_code in (401, 403, 422)

    def test_scans_versioned(self, client: TestClient) -> None:
        """GET /api/v1/scans requires auth."""
        response = client.get("/api/v1/scans")
        assert response.status_code == 403

    def test_search_ingredient_versioned(self, client: TestClient) -> None:
        """GET /api/v1/search/ingredient is public."""
        response = client.get(
            "/api/v1/search/ingredient",
            params={"query": "NONEXISTENT12345"},
        )
        assert response.status_code in (200, 404, 500)

    def test_search_ingredients_bulk_versioned(self, client: TestClient) -> None:
        """POST /api/v1/search/ingredients is public."""
        response = client.post(
            "/api/v1/search/ingredients",
            json={"ingredients": ["Water"]},
        )
        assert response.status_code in (200, 500)

    def test_knowledge_ingredient_versioned(self, client: TestClient) -> None:
        """GET /api/v1/knowledge/ingredient/{id} is public."""
        response = client.get(
            "/api/v1/knowledge/ingredient/nonexistent-id",
        )
        assert response.status_code in (200, 404, 500)

    def test_admin_safety_profiles_versioned(self, client: TestClient) -> None:
        """GET /api/v1/admin/safety-profiles/{id} requires admin auth."""
        response = client.get(
            "/api/v1/admin/safety-profiles/nonexistent-id",
        )
        assert response.status_code == 403

    def test_admin_regulations_versioned(self, client: TestClient) -> None:
        """GET /api/v1/admin/regulations requires admin auth."""
        response = client.get("/api/v1/admin/regulations")
        assert response.status_code == 403

    def test_admin_scientific_references_versioned(
        self, client: TestClient
    ) -> None:
        """GET /api/v1/admin/scientific-references requires admin auth."""
        response = client.get("/api/v1/admin/scientific-references")
        assert response.status_code == 403

    def test_admin_dashboard_versioned(self, client: TestClient) -> None:
        """GET /api/v1/admin/dashboard requires admin auth."""
        response = client.get("/api/v1/admin/dashboard")
        assert response.status_code == 403


# ===========================================================================
# SECTION B — Health Endpoints Remain Unversioned
# ===========================================================================


class TestHealthEndpointsUnversioned:
    """Health endpoints must be accessible at /health, not /api/v1/health."""

    def test_health_unversioned(self, client: TestClient) -> None:
        """GET /health returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"

    def test_health_database_unversioned(self, client: TestClient) -> None:
        """GET /health/database returns 200 or 503."""
        response = client.get("/health/database")
        assert response.status_code in (200, 503)

    def test_health_not_under_api_v1(self, client: TestClient) -> None:
        """GET /api/v1/health should return 404 (not mounted there)."""
        response = client.get("/api/v1/health")
        assert response.status_code == 404


# ===========================================================================
# SECTION C — Authentication Through Versioned Path
# ===========================================================================


class TestVersionedAuthentication:
    """Authentication flow must work correctly through /api/v1/ paths."""

    def test_validation_error_on_versioned_register(
        self, client: TestClient
    ) -> None:
        """Empty body on /api/v1/auth/register returns 422."""
        response = client.post("/api/v1/auth/register", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body

    def test_validation_error_on_versioned_login(
        self, client: TestClient
    ) -> None:
        """Empty body on /api/v1/auth/login returns 422."""
        response = client.post("/api/v1/auth/login", json={})
        assert response.status_code == 422
        body = response.json()
        assert "detail" in body

    def test_invalid_email_on_versioned_register(
        self, client: TestClient
    ) -> None:
        """Invalid email on /api/v1/auth/register returns 422."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "username": "testuser",
                "password": "StrongPass123",
            },
        )
        assert response.status_code == 422


# ===========================================================================
# SECTION D — Protected Routes Enforce Auth Through Versioned Path
# ===========================================================================


class TestVersionedProtectedRoutes:
    """Protected endpoints must still require authentication under /api/v1/."""

    def test_users_me_no_token(self, client: TestClient) -> None:
        """GET /api/v1/users/me without token returns 403."""
        response = client.get("/api/v1/users/me")
        assert response.status_code == 403

    def test_users_me_invalid_token(self, client: TestClient) -> None:
        """GET /api/v1/users/me with bad token returns 401."""
        response = client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    def test_admin_no_token(self, client: TestClient) -> None:
        """GET /api/v1/admin/ingredients without token returns 403."""
        response = client.get("/api/v1/admin/ingredients")
        assert response.status_code == 403

    def test_admin_invalid_token(self, client: TestClient) -> None:
        """GET /api/v1/admin/ingredients with bad token returns 401."""
        response = client.get(
            "/api/v1/admin/ingredients",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 401

    def test_scan_no_token(self, client: TestClient) -> None:
        """POST /api/v1/scan/analyze without token returns 403."""
        response = client.post(
            "/api/v1/scan/analyze",
            json={"ingredients": ["Water"]},
        )
        assert response.status_code in (401, 403)

    def test_scans_no_token(self, client: TestClient) -> None:
        """GET /api/v1/scans without token returns 403."""
        response = client.get("/api/v1/scans")
        assert response.status_code == 403


# ===========================================================================
# SECTION E — Backward Compatibility (Unversioned Paths Still Work)
# ===========================================================================


class TestBackwardCompatibility:
    """Old unversioned paths must continue to work for existing clients."""

    def test_unversioned_auth_register(self, client: TestClient) -> None:
        """POST /auth/register still works."""
        response = client.post("/auth/register", json={})
        assert response.status_code == 422

    def test_unversioned_auth_login(self, client: TestClient) -> None:
        """POST /auth/login still works."""
        response = client.post("/auth/login", json={})
        assert response.status_code == 422

    def test_unversioned_users_me(self, client: TestClient) -> None:
        """GET /users/me still requires auth."""
        response = client.get("/users/me")
        assert response.status_code == 403

    def test_unversioned_admin_ingredients(self, client: TestClient) -> None:
        """GET /admin/ingredients still requires admin auth."""
        response = client.get("/admin/ingredients")
        assert response.status_code == 403

    def test_unversioned_scan_analyze(self, client: TestClient) -> None:
        """POST /scan/analyze still requires auth."""
        response = client.post(
            "/scan/analyze",
            json={"ingredients": []},
        )
        assert response.status_code in (401, 403, 422)

    def test_unversioned_scans(self, client: TestClient) -> None:
        """GET /scans still requires auth."""
        response = client.get("/scans")
        assert response.status_code == 403

    def test_unversioned_search_ingredient(self, client: TestClient) -> None:
        """GET /search/ingredient still works."""
        response = client.get(
            "/search/ingredient",
            params={"query": "NONEXISTENT"},
        )
        assert response.status_code in (200, 404, 500)

    def test_unversioned_health(self, client: TestClient) -> None:
        """GET /health still works."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_unversioned_root(self, client: TestClient) -> None:
        """GET / still works."""
        response = client.get("/")
        assert response.status_code == 200
        body = response.json()
        assert "message" in body


# ===========================================================================
# SECTION F — API Version Metadata
# ===========================================================================


class TestAPIVersionMetadata:
    """Verify the /api/version metadata endpoint."""

    def test_version_endpoint_exists(self, client: TestClient) -> None:
        """GET /api/version returns version info."""
        response = client.get("/api/version")
        assert response.status_code == 200

    def test_version_endpoint_structure(self, client: TestClient) -> None:
        """Version endpoint returns correct structure."""
        response = client.get("/api/version")
        body = response.json()
        assert "current" in body
        assert "available" in body
        assert body["current"] == "v1"
        assert "v1" in body["available"]

    def test_version_endpoint_docs_link(self, client: TestClient) -> None:
        """Version endpoint includes docs link."""
        response = client.get("/api/version")
        body = response.json()
        assert "docs" in body
        assert body["docs"] == "/docs"


# ===========================================================================
# SECTION G — Route Structure Integrity
# ===========================================================================


class TestRouteStructureIntegrity:
    """Verify that the versioned and unversioned routes produce identical behavior."""

    def test_versioned_auth_validation_matches_unversioned(
        self, client: TestClient
    ) -> None:
        """Both paths return same validation error structure."""
        v1_response = client.post("/api/v1/auth/register", json={})
        legacy_response = client.post("/auth/register", json={})
        assert v1_response.status_code == legacy_response.status_code == 422
        v1_body = v1_response.json()
        legacy_body = legacy_response.json()
        assert "detail" in v1_body
        assert "detail" in legacy_body
        assert isinstance(v1_body["detail"], list)
        assert isinstance(legacy_body["detail"], list)

    def test_versioned_admin_auth_matches_unversioned(
        self, client: TestClient
    ) -> None:
        """Both paths return same auth error structure."""
        v1_response = client.get("/api/v1/admin/ingredients")
        legacy_response = client.get("/admin/ingredients")
        assert v1_response.status_code == legacy_response.status_code == 403
        v1_body = v1_response.json()
        legacy_body = legacy_response.json()
        assert "detail" in v1_body
        assert "detail" in legacy_body

    def test_versioned_users_auth_matches_unversioned(
        self, client: TestClient
    ) -> None:
        """Both paths return same auth error structure for /users/me."""
        v1_response = client.get("/api/v1/users/me")
        legacy_response = client.get("/users/me")
        assert v1_response.status_code == legacy_response.status_code == 403

    def test_versioned_scans_auth_matches_unversioned(
        self, client: TestClient
    ) -> None:
        """Both paths return same auth error structure for /scans."""
        v1_response = client.get("/api/v1/scans")
        legacy_response = client.get("/scans")
        assert v1_response.status_code == legacy_response.status_code == 403

    def test_no_route_collision_on_health(self, client: TestClient) -> None:
        """Health endpoint is not duplicated under /api/v1/."""
        response = client.get("/api/v1/health")
        assert response.status_code == 404
        response = client.get("/health")
        assert response.status_code == 200

    def test_openapi_contains_versioned_routes(self, client: TestClient) -> None:
        """OpenAPI schema includes versioned route paths."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema.get("paths", {})
        versioned_paths = [p for p in paths if p.startswith("/api/v1/")]
        assert len(versioned_paths) > 0, "No /api/v1/ paths found in OpenAPI"

    def test_openapi_contains_unversioned_routes(self, client: TestClient) -> None:
        """OpenAPI schema still includes backward-compatible unversioned paths."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        paths = schema.get("paths", {})
        unversioned_api_paths = [
            p for p in paths
            if not p.startswith("/api/v1/")
            and not p.startswith("/api/")
            and p not in ("/health", "/health/database", "/")
        ]
        assert len(unversioned_api_paths) > 0, (
            "No unversioned API paths found — backward compatibility may be broken"
        )

    def test_security_headers_present_on_versioned_routes(
        self, client: TestClient
    ) -> None:
        """Security headers must be present on versioned routes."""
        response = client.get("/api/v1/users/me")
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
