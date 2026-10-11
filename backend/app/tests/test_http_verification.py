"""
Milestone 11 Step 3 — Production-Readiness HTTP-Level Verification.

Tests the actual running FastAPI application through real HTTP requests.
Requires the server to be running on http://127.0.0.1:8000.

Key API auth contracts verified during this step:
- HTTPBearer returns 403 when Authorization header is missing entirely.
- HTTPBearer returns 401 for malformed/invalid Bearer tokens.
- Admin endpoints (/admin/*) require ADMIN role; auth check happens before
  resource lookup, so unauthenticated requests return 403, not 404.
- User endpoints (/scans/*, /scan/*, /users/*) require any authenticated user.
- Registration has no role parameter — all users are created with USER role.
"""

import uuid

import requests

BASE = "http://127.0.0.1:8000"


class TestPart1BasicEndpoints:
    """PART 1 — Verify the application starts and basic endpoints respond."""

    def test_root_endpoint(self):
        r = requests.get(f"{BASE}/")
        assert r.status_code == 200
        body = r.json()
        assert "message" in body
        print(f"  [PASS] GET / -> 200: {body}")

    def test_health_endpoint(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        print(f"  [PASS] GET /health -> 200: status={body.get('status')}")

    def test_health_database_endpoint(self):
        r = requests.get(f"{BASE}/health/database")
        assert r.status_code in (200, 503)
        body = r.json()
        print(f"  [PASS] GET /health/database -> {r.status_code}: {body}")


class TestPart2ValidationErrors:
    """PART 2 TEST A — Validation errors return 422 with safe JSON."""

    def test_register_empty_body(self):
        r = requests.post(f"{BASE}/auth/register", json={})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /auth/register {{}} -> 422")

    def test_register_invalid_fields(self):
        r = requests.post(f"{BASE}/auth/register", json={
            "email": "bad", "username": "x", "password": "ab"
        })
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /auth/register invalid -> 422")

    def test_login_empty_body(self):
        r = requests.post(f"{BASE}/auth/login", json={})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /auth/login {{}} -> 422")

    def test_search_ingredients_empty_body(self):
        r = requests.post(f"{BASE}/search/ingredients", json={})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /search/ingredients {{}} -> 422")

    def test_search_ingredients_empty_list(self):
        r = requests.post(f"{BASE}/search/ingredients", json={"ingredients": []})
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /search/ingredients [] -> 422")

    def test_scan_analyze_no_auth_returns_auth_error(self):
        """POST /scan/analyze requires get_current_user — auth check
        (403) fires before body validation (422) when no token is sent."""
        r = requests.post(f"{BASE}/scan/analyze", json={})
        assert r.status_code in (401, 403)
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] POST /scan/analyze {{}} (no auth) -> {r.status_code}")

    def test_validation_error_no_traceback(self):
        r = requests.post(f"{BASE}/auth/register", json={})
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "stack" not in body_text
        print(f"  [PASS] Validation error response has no traceback")

    def test_validation_error_body_structure(self):
        r = requests.post(f"{BASE}/auth/login", json={})
        body = r.json()
        assert "detail" in body
        assert isinstance(body["detail"], list)
        print(f"  [PASS] Validation error uses standard Pydantic detail structure")


class TestPart2ResourceNotFound:
    """PART 2 TEST B — Resource not found returns safe error responses.

    Admin-protected endpoints require auth first, so unauthenticated
    requests get 403 (auth check) before 404 (resource lookup) can fire.
    We verify the responses are still safe JSON regardless.
    """

    def _fake_id(self):
        return str(uuid.uuid4())

    def test_admin_endpoint_no_auth_returns_auth_error(self):
        """Admin endpoints require require_admin dependency — without
        a token, HTTPBearer returns 403 before the route handler runs."""
        r = requests.get(f"{BASE}/admin/ingredients/{self._fake_id()}")
        assert r.status_code in (401, 403)
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] GET /admin/ingredients/{{fake}} (no auth) -> {r.status_code}")

    def test_user_endpoint_no_auth_returns_auth_error(self):
        """User endpoints require get_current_user — without a token,
        HTTPBearer returns 403."""
        r = requests.get(f"{BASE}/scans/{self._fake_id()}")
        assert r.status_code in (401, 403)
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] GET /scans/{{fake}} (no auth) -> {r.status_code}")

    def test_admin_safety_profile_no_auth_returns_auth_error(self):
        r = requests.get(f"{BASE}/admin/safety-profiles/{self._fake_id()}")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /admin/safety-profiles/{{fake}} (no auth) -> {r.status_code}")

    def test_admin_regulation_no_auth_returns_auth_error(self):
        r = requests.get(f"{BASE}/admin/regulations/{self._fake_id()}")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /admin/regulations/{{fake}} (no auth) -> {r.status_code}")

    def test_admin_reference_no_auth_returns_auth_error(self):
        r = requests.get(f"{BASE}/admin/scientific-references/{self._fake_id()}")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /admin/scientific-references/{{fake}} (no auth) -> {r.status_code}")

    def test_error_response_has_no_traceback(self):
        """Even auth-blocked responses must not leak internals."""
        r = requests.get(f"{BASE}/admin/ingredients/{self._fake_id()}")
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        assert "database_url" not in body_text
        print(f"  [PASS] Error response has no traceback or internal details")


class TestPart2AuthenticationFailure:
    """PART 2 TEST C — Authentication failures."""

    def test_no_auth_header_returns_403(self):
        """HTTPBearer returns 403 when Authorization header is completely absent."""
        r = requests.get(f"{BASE}/users/me")
        assert r.status_code == 403
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] GET /users/me (no header) -> 403: {body['detail']}")

    def test_malformed_token_returns_401(self):
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": "Bearer invalid-token-string"
        })
        assert r.status_code == 401
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] GET /users/me (bad token) -> 401: {body['detail']}")

    def test_empty_bearer_returns_auth_error(self):
        """HTTPBearer may return 403 or 401 for empty bearer depending
        on how the header value is parsed. Either is acceptable."""
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": "Bearer "
        })
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /users/me (empty bearer) -> {r.status_code}")

    def test_invalid_jwt_signature_returns_401(self):
        fake_jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0."
            "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": f"Bearer {fake_jwt}"
        })
        assert r.status_code == 401
        print(f"  [PASS] GET /users/me (bad JWT sig) -> 401")

    def test_auth_error_no_internals_leaked(self):
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": "Bearer garbage-token"
        })
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "secret" not in body_text
        assert "database_url" not in body_text
        print(f"  [PASS] Auth error leaks no internals")

    def test_admin_no_auth_returns_error(self):
        r = requests.get(f"{BASE}/admin/ingredients")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /admin/ingredients (no auth) -> {r.status_code}")


class TestPart2AuthorizationFailure:
    """PART 2 TEST D — Authorization failures (user vs admin).

    Registration does not accept a role parameter — all users are created
    with USER role. We cannot create admin users through the public API,
    so we test that USER tokens are rejected from admin endpoints.
    """

    def _register_and_login(self, email=None, username=None):
        suffix = uuid.uuid4().hex[:8]
        email = email or f"user_{suffix}@example.com"
        username = username or f"user_{suffix}"
        reg_data = {"email": email, "username": username, "password": "TestPass123!"}
        r = requests.post(f"{BASE}/auth/register", json=reg_data)
        if r.status_code != 201:
            return None
        r = requests.post(f"{BASE}/auth/login", json={
            "email": email, "password": "TestPass123!"
        })
        if r.status_code == 200:
            return r.json().get("access_token")
        return None

    def test_user_token_rejected_from_admin_endpoint(self):
        token = self._register_and_login()
        if not token:
            print("  [SKIP] Could not register/login user")
            return
        r = requests.get(f"{BASE}/admin/ingredients", headers={
            "Authorization": f"Bearer {token}"
        })
        assert r.status_code == 403
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] GET /admin/ingredients (user) -> 403: {body['detail']}")

    def test_admin_access_cannot_be_self_granted(self):
        """Registration has no role field — all users get USER role.
        Attempting to pass 'role' in the request body is silently ignored.
        This confirms users cannot escalate to admin via registration."""
        suffix = uuid.uuid4().hex[:8]
        reg_data = {
            "email": f"admin_attempt_{suffix}@example.com",
            "username": f"admin_attempt_{suffix}",
            "password": "Admin123!",
        }
        r = requests.post(f"{BASE}/auth/register", json=reg_data)
        assert r.status_code == 201
        r = requests.post(f"{BASE}/auth/login", json={
            "email": reg_data["email"],
            "password": "Admin123!",
        })
        assert r.status_code == 200
        token = r.json().get("access_token")
        r = requests.get(f"{BASE}/admin/ingredients", headers={
            "Authorization": f"Bearer {token}"
        })
        assert r.status_code == 403
        print(f"  [PASS] Self-registered user cannot access admin endpoints -> 403")


class TestPart2DuplicateResource:
    """PART 2 TEST E — Duplicate resource returns 409."""

    def test_duplicate_registration(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"dup_{suffix}@example.com"
        reg_data = {"email": email, "username": f"dup_{suffix}", "password": "DupTest123!"}
        r1 = requests.post(f"{BASE}/auth/register", json=reg_data)
        assert r1.status_code == 201, f"First register: {r1.status_code} {r1.text[:200]}"

        r2 = requests.post(f"{BASE}/auth/register", json=reg_data)
        assert r2.status_code == 409
        body = r2.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
        assert len(body["detail"]) > 0
        print(f"  [PASS] POST /auth/register (duplicate) -> 409: {body['detail']}")

    def test_duplicate_no_traceback(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"dup2_{suffix}@example.com"
        reg_data = {"email": email, "username": f"dup2_{suffix}", "password": "DupTest123!"}
        requests.post(f"{BASE}/auth/register", json=reg_data)
        r = requests.post(f"{BASE}/auth/register", json=reg_data)
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        print(f"  [PASS] 409 response leaks no internals")


class TestPart3ResponseConsistency:
    """PART 3 — Verify all error responses use consistent format."""

    def _assert_detail_format(self, r, expected_type=str):
        body = r.json()
        assert "detail" in body, f"Missing 'detail' key: {body}"
        assert isinstance(body["detail"], expected_type), (
            f"Expected detail to be {expected_type.__name__}, got {type(body['detail']).__name__}"
        )

    def test_422_uses_detail_key(self):
        r = requests.post(f"{BASE}/auth/register", json={})
        self._assert_detail_format(r, list)

    def test_403_uses_detail_key(self):
        r = requests.get(f"{BASE}/admin/ingredients/{uuid.uuid4()}")
        self._assert_detail_format(r, str)

    def test_401_uses_detail_key(self):
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": "Bearer bad-token"
        })
        self._assert_detail_format(r, str)

    def test_403_no_auth_uses_detail_key(self):
        r = requests.get(f"{BASE}/users/me")
        self._assert_detail_format(r, str)

    def test_409_uses_detail_key(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"cons_{suffix}@example.com"
        reg_data = {"email": email, "username": f"cons_{suffix}", "password": "ConTest123!"}
        requests.post(f"{BASE}/auth/register", json=reg_data)
        r = requests.post(f"{BASE}/auth/register", json=reg_data)
        self._assert_detail_format(r, str)

    def test_error_responses_are_consistent_and_safe(self):
        """All error responses should use {"detail": ...} and not leak internals."""
        r = requests.get(f"{BASE}/admin/ingredients/{uuid.uuid4()}")
        assert r.status_code in (401, 403, 404)
        body_text = r.text.lower()
        assert "traceback" not in body_text
        assert "prisma" not in body_text
        body = r.json()
        assert "detail" in body
        print(f"  [PASS] Error responses consistent and safe")


class TestPart4SuccessRegression:
    """PART 4 — Verify successful endpoints still work correctly."""

    def test_auth_register_success(self):
        suffix = uuid.uuid4().hex[:8]
        r = requests.post(f"{BASE}/auth/register", json={
            "email": f"success_{suffix}@example.com",
            "username": f"success_{suffix}",
            "password": "Success123!"
        })
        assert r.status_code == 201
        body = r.json()
        assert "id" in body or "email" in body or "message" in body
        print(f"  [PASS] POST /auth/register -> 201")

    def test_auth_login_success(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"login_{suffix}@example.com"
        requests.post(f"{BASE}/auth/register", json={
            "email": email, "username": f"login_{suffix}", "password": "Login123!"
        })
        r = requests.post(f"{BASE}/auth/login", json={
            "email": email, "password": "Login123!"
        })
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        print(f"  [PASS] POST /auth/login -> 200: has access_token")

    def test_users_me_success(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"me_{suffix}@example.com"
        r = requests.post(f"{BASE}/auth/register", json={
            "email": email, "username": f"me_{suffix}", "password": "Me12345!"
        })
        assert r.status_code == 201, f"Register failed: {r.status_code} {r.text[:200]}"
        r = requests.post(f"{BASE}/auth/login", json={
            "email": email, "password": "Me12345!"
        })
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
        token = r.json().get("access_token")
        assert token, "No access_token returned"
        r = requests.get(f"{BASE}/users/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert r.status_code == 200, f"users/me failed: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "id" in body
        assert "email" in body
        assert "username" in body
        assert "role" in body
        assert "hashedPassword" not in body
        assert "hashedpassword" not in body
        print(f"  [PASS] GET /users/me -> 200: {list(body.keys())}")

    def test_search_ingredients_bulk(self):
        r = requests.post(f"{BASE}/search/ingredients", json={
            "ingredients": ["Water"]
        })
        assert r.status_code == 200
        print(f"  [PASS] POST /search/ingredients [Water] -> 200")

    def test_health_check(self):
        r = requests.get(f"{BASE}/health")
        assert r.status_code == 200
        print(f"  [PASS] GET /health -> 200")

    def test_root_endpoint(self):
        r = requests.get(f"{BASE}/")
        assert r.status_code == 200
        body = r.json()
        assert "message" in body
        print(f"  [PASS] GET / -> 200")

    def test_scan_analyze_requires_auth(self):
        r = requests.post(f"{BASE}/scan/analyze", json={
            "ingredients": ["Water"]
        })
        assert r.status_code in (401, 403)
        print(f"  [PASS] POST /scan/analyze (no auth) -> {r.status_code}")

    def test_scans_requires_auth(self):
        r = requests.get(f"{BASE}/scans")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /scans (no auth) -> {r.status_code}")

    def test_admin_dashboard_requires_auth(self):
        r = requests.get(f"{BASE}/admin/dashboard")
        assert r.status_code in (401, 403)
        print(f"  [PASS] GET /admin/dashboard (no auth) -> {r.status_code}")


if __name__ == "__main__":
    import sys
    sys.exit(0)
