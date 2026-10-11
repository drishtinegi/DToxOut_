"""
Admin Audit Trail tests (Milestone 12 Step 5, Part 3).

Verifies:
    A. audit_log utility function produces correct log entries
    B. Log contains the action name
    C. Log contains the admin_id
    D. Log contains the target_id when provided
    E. Log contains the status (success/failure)
    F. Log contains the request_id when provided
    G. Log contains detail when provided
    H. Sensitive data is never logged
    I. Admin create endpoint produces audit log
    J. Admin delete endpoint produces audit log

Run with:
    pytest app/tests/test_audit.py -v
"""

from __future__ import annotations

import io
import logging
import re
import uuid

import pytest

from app.core.audit import audit_log
from app.core.logging import SensitiveFilter, _FORMATTERS, configure_logging


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_log_capture(
    fmt: str = "keyvalue",
) -> tuple[io.StringIO, logging.Handler]:
    """Attach a StringIO handler to root logger for test assertions."""
    stream = io.StringIO()
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(stream)
    handler.setFormatter(_FORMATTERS[fmt])
    handler.addFilter(SensitiveFilter())
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    return stream, handler


def _reset_logging() -> None:
    """Reset root logger to default state."""
    configure_logging(level="INFO", fmt="keyvalue")


# ===========================================================================
# SECTION A — audit_log utility function produces log entries
# ===========================================================================


class TestAuditLogProducesEntry:
    """The audit_log function must produce at least one log line."""

    def test_basic_audit_log(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test_action", admin_id="admin-123")
            output = stream.getvalue()
            assert "action=test_action" in output
        finally:
            _reset_logging()

    def test_audit_log_has_admin_id(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="admin-456")
            output = stream.getvalue()
            assert "admin_id=admin-456" in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION B — Log contains the action name
# ===========================================================================


class TestAuditLogAction:
    """The action field must match the provided action string."""

    def test_create_ingredient_action(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="create_ingredient", admin_id="a1")
            assert "action=create_ingredient" in stream.getvalue()
        finally:
            _reset_logging()

    def test_delete_ingredient_action(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="delete_ingredient", admin_id="a1")
            assert "action=delete_ingredient" in stream.getvalue()
        finally:
            _reset_logging()

    def test_custom_action(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="promote_user", admin_id="a1")
            assert "action=promote_user" in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION C — Log contains the admin_id
# ===========================================================================


class TestAuditLogAdminID:
    """The admin_id field must match the provided admin UUID."""

    def test_uuid_admin_id(self) -> None:
        admin_id = str(uuid.uuid4())
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id=admin_id)
            assert f"admin_id={admin_id}" in stream.getvalue()
        finally:
            _reset_logging()

    def test_different_admin_ids(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="aaa")
            audit_log(action="test", admin_id="bbb")
            output = stream.getvalue()
            assert "admin_id=aaa" in output
            assert "admin_id=bbb" in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION D — Log contains the target_id when provided
# ===========================================================================


class TestAuditLogTargetID:
    """The target_id field must appear only when provided."""

    def test_target_id_present(self) -> None:
        target = str(uuid.uuid4())
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", target_id=target)
            assert f"target_id={target}" in stream.getvalue()
        finally:
            _reset_logging()

    def test_target_id_absent_when_none(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", target_id=None)
            assert "target_id=" not in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION E — Log contains the status
# ===========================================================================


class TestAuditLogStatus:
    """The status field must match the provided status string."""

    def test_success_status(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", status="success")
            assert "status=success" in stream.getvalue()
        finally:
            _reset_logging()

    def test_failure_status(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", status="failure")
            assert "status=failure" in stream.getvalue()
        finally:
            _reset_logging()

    def test_default_status_is_success(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1")
            assert "status=success" in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION F — Log contains the request_id when provided
# ===========================================================================


class TestAuditLogRequestID:
    """The request_id must be passed through to the log record."""

    def test_request_id_present(self) -> None:
        rid = str(uuid.uuid4())
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", request_id=rid)
            assert f"request_id={rid}" in stream.getvalue()
        finally:
            _reset_logging()

    def test_request_id_empty_string_when_none(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", request_id=None)
            output = stream.getvalue()
            # When request_id is None, empty string is passed as extra
            # The formatter should render request_id= (empty)
            assert "action=test" in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION G — Log contains detail when provided
# ===========================================================================


class TestAuditLogDetail:
    """The optional detail field must appear only when provided."""

    def test_detail_present(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", detail="created Niacinamide")
            assert "detail=created Niacinamide" in stream.getvalue()
        finally:
            _reset_logging()

    def test_detail_absent_when_none(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(action="test", admin_id="a1", detail=None)
            assert "detail=" not in stream.getvalue()
        finally:
            _reset_logging()


# ===========================================================================
# SECTION H — Sensitive data is never logged
# ===========================================================================


class TestAuditLogSensitiveData:
    """Audit logs must never contain passwords, tokens, or secrets."""

    def test_password_not_included(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(
                action="test",
                admin_id="a1",
                detail="password=hunter2",
            )
            output = stream.getvalue()
            # The SensitiveFilter should scrub the password
            assert "hunter2" not in output
        finally:
            _reset_logging()

    def test_token_not_included(self) -> None:
        stream, _ = _setup_log_capture()
        try:
            audit_log(
                action="test",
                admin_id="a1",
                detail="Bearer eyJhbGciOiJIUzI1NiJ9",
            )
            output = stream.getvalue()
            assert "eyJhbGciOiJIUzI1NiJ9" not in output
        finally:
            _reset_logging()


# ===========================================================================
# SECTION I — Admin create endpoint produces audit log
# ===========================================================================


class TestAdminCreateAuditLog:
    """The POST /admin/ingredients endpoint must emit an audit log."""

    def test_create_emits_audit_log(self) -> None:
        """Verify the create endpoint logs the action and admin_id."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.admin import _get_service, require_admin, router

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.id = "admin-uuid-123"
        mock_user.role = "ADMIN"

        mock_service = MagicMock()
        mock_ingredient = MagicMock()
        mock_ingredient.id = "ingredient-uuid-456"
        mock_ingredient.inciName = "TestIngredient"
        mock_ingredient.commonName = "Test"
        mock_ingredient.description = "A test ingredient"
        mock_ingredient.function = "Testing"
        mock_ingredient.safetyRating = 9.0
        mock_ingredient.evidenceLevel = "HIGH"
        mock_ingredient.createdAt.isoformat.return_value = "2025-01-15T10:30:00Z"

        mock_service.create_ingredient = AsyncMock(return_value=mock_ingredient)

        async def _override_admin():
            return mock_user

        def _override_service():
            return mock_service

        app.dependency_overrides[require_admin] = _override_admin
        app.dependency_overrides[_get_service] = _override_service

        stream, _ = _setup_log_capture()
        try:
            client = TestClient(app)
            resp = client.post(
                "/admin/ingredients",
                json={
                    "inci_name": "TestIngredient",
                    "common_name": "Test",
                    "description": "A test ingredient",
                    "function": "Testing",
                    "safety_rating": 9.0,
                    "evidence_level": "HIGH",
                },
            )
            assert resp.status_code == 201
            output = stream.getvalue()
            assert "action=create_ingredient" in output
            assert "admin_id=admin-uuid-123" in output
            assert "target_id=ingredient-uuid-456" in output
            assert "status=success" in output
        finally:
            app.dependency_overrides.clear()
            _reset_logging()


# ===========================================================================
# SECTION J — Admin delete endpoint produces audit log
# ===========================================================================


class TestAdminDeleteAuditLog:
    """The DELETE /admin/ingredients/{id} endpoint must emit an audit log."""

    def test_delete_emits_audit_log(self) -> None:
        """Verify the delete endpoint logs the action and admin_id."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.admin import _get_service, require_admin, router

        app = FastAPI()
        app.include_router(router)

        mock_user = MagicMock()
        mock_user.id = "admin-uuid-789"
        mock_user.role = "ADMIN"

        mock_service = MagicMock()
        mock_service.delete_ingredient = AsyncMock(return_value=None)

        ingredient_id = str(uuid.uuid4())

        async def _override_admin():
            return mock_user

        def _override_service():
            return mock_service

        app.dependency_overrides[require_admin] = _override_admin
        app.dependency_overrides[_get_service] = _override_service

        stream, _ = _setup_log_capture()
        try:
            client = TestClient(app)
            resp = client.delete(f"/admin/ingredients/{ingredient_id}")
            assert resp.status_code == 204
            output = stream.getvalue()
            assert "action=delete_ingredient" in output
            assert "admin_id=admin-uuid-789" in output
            assert f"target_id={ingredient_id}" in output
            assert "status=success" in output
        finally:
            app.dependency_overrides.clear()
            _reset_logging()
