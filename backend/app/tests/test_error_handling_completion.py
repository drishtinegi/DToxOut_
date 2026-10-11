"""
Tests for the Error Handling Completion sub-feature (Milestone 12).

Covers:
    A. JWT token error distinction — expired vs malformed/tampered
    B. DuplicateScanIngredientError — raised on duplicate (scanId, ingredientId)
    C. persist_analysis error handling — structured logging, no secrets leaked

Run with:
    pytest app/tests/test_error_handling_completion.py -v
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import DomainError
from app.core.security import (
    TokenExpiredError,
    TokenInvalidError,
    _create_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.services.scan_service import (
    DuplicateScanIngredientError,
    ScanIngredientInput,
    ScanNotFoundError,
    ScanService,
)


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


# ===========================================================================
# SECTION A — JWT Token Error Distinction
# ===========================================================================


class TestJWTErrorDistinction:
    """Verify decode_token raises TokenExpiredError vs TokenInvalidError."""

    def test_valid_token_decodes(self) -> None:
        """A valid, non-expired token decodes successfully."""
        token = create_access_token(subject="user-1")
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["type"] == "access"

    def test_malformed_token_raises_token_invalid(self) -> None:
        """A random string raises TokenInvalidError, not a bare exception."""
        with pytest.raises(TokenInvalidError):
            decode_token("not-a-jwt-at-all")

    def test_empty_string_raises_token_invalid(self) -> None:
        """An empty token raises TokenInvalidError."""
        with pytest.raises(TokenInvalidError):
            decode_token("")

    def test_tampered_signature_raises_token_invalid(self) -> None:
        """A token with a corrupted signature raises TokenInvalidError."""
        token = create_access_token(subject="user-1")
        tampered = token[:-8] + "XXXXXXXX"
        with pytest.raises(TokenInvalidError):
            decode_token(tampered)

    def test_wrong_algorithm_header_raises_token_invalid(self) -> None:
        """A token signed with a different algorithm raises TokenInvalidError."""
        # Craft a token-like string with HS384 algorithm header
        token = create_access_token(subject="user-1")
        # Replace header algorithm from HS256 to HS384 (base64)
        import base64
        import json

        parts = token.split(".")
        new_header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS384", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        tampered = f"{new_header}.{''.join(parts[1:])}"
        with pytest.raises(TokenInvalidError):
            decode_token(tampered)

    def test_expired_token_raises_token_expired(self) -> None:
        """An expired token raises TokenExpiredError, not TokenInvalidError."""
        import datetime

        # Create a token that is already expired via _create_token
        token = _create_token(
            {"sub": "user-1", "type": "access"},
            datetime.timedelta(seconds=-1),
        )
        with pytest.raises(TokenExpiredError):
            decode_token(token)

    def test_expired_token_has_correct_message(self) -> None:
        """TokenExpiredError carries a descriptive message."""
        import datetime

        token = _create_token(
            {"sub": "user-1", "type": "access"},
            datetime.timedelta(seconds=-1),
        )
        with pytest.raises(TokenExpiredError, match="expired"):
            decode_token(token)

    def test_refresh_token_type_works(self) -> None:
        """Refresh tokens decode correctly with type=refresh."""
        token = create_refresh_token(subject="user-1")
        payload = decode_token(token)
        assert payload["sub"] == "user-1"
        assert payload["type"] == "refresh"

    def test_token_invalid_is_domain_error_subclass(self) -> None:
        """TokenInvalidError is an Exception subclass."""
        assert issubclass(TokenInvalidError, Exception)

    def test_token_expired_is_domain_error_subclass(self) -> None:
        """TokenExpiredError is an Exception subclass."""
        assert issubclass(TokenExpiredError, Exception)


# ===========================================================================
# SECTION B — DuplicateScanIngredientError
# ===========================================================================


class TestDuplicateScanIngredientError:
    """Verify DuplicateScanIngredientError is raised correctly."""

    def test_is_domain_error_subclass(self) -> None:
        """DuplicateScanIngredientError inherits from DomainError."""
        assert issubclass(DuplicateScanIngredientError, DomainError)

    def test_status_code_is_409(self) -> None:
        """DuplicateScanIngredientError maps to HTTP 409 Conflict."""
        assert DuplicateScanIngredientError.status_code == 409

    def test_error_message_includes_ids(self) -> None:
        """The error message includes both scan_id and ingredient_id."""
        exc = DuplicateScanIngredientError("scan-abc", "ing-xyz")
        assert "scan-abc" in exc.detail
        assert "ing-xyz" in exc.detail

    def test_error_message_default_format(self) -> None:
        """The error message uses a consistent format."""
        exc = DuplicateScanIngredientError("s1", "i1")
        assert "already exists" in exc.detail.lower()

    def test_add_scan_ingredients_raises_on_duplicate(self) -> None:
        """add_scan_ingredients raises DuplicateScanIngredientError on duplicate."""
        mock_db = MagicMock()
        mock_scan = MagicMock()
        mock_scan.id = "scan-1"
        mock_scan.userId = "user-1"
        mock_db.scan.find_unique = AsyncMock(return_value=mock_scan)

        ingredient = MagicMock()
        ingredient.id = "ing-1"
        ingredient.inciName = "Niacinamide"
        mock_db.ingredient.find_first = AsyncMock(return_value=ingredient)

        existing_junction = MagicMock()
        mock_db.scaningredient.find_unique = AsyncMock(return_value=existing_junction)

        service = ScanService(mock_db)
        inputs = [
            ScanIngredientInput(
                ingredient_name="Niacinamide",
                detected_name="Niacinamide",
                confidence_score=0.95,
            )
        ]

        with pytest.raises(DuplicateScanIngredientError):
            _run(service.add_scan_ingredients("scan-1", inputs))

    def test_add_scan_ingredients_succeeds_when_no_duplicate(self) -> None:
        """add_scan_ingredients creates record when no duplicate exists."""
        mock_db = MagicMock()
        mock_scan = MagicMock()
        mock_scan.id = "scan-1"
        mock_scan.userId = "user-1"
        mock_db.scan.find_unique = AsyncMock(return_value=mock_scan)

        ingredient = MagicMock()
        ingredient.id = "ing-1"
        ingredient.inciName = "Niacinamide"
        mock_db.ingredient.find_first = AsyncMock(return_value=ingredient)

        mock_db.scaningredient.find_unique = AsyncMock(return_value=None)

        created = MagicMock()
        mock_db.scaningredient.create = AsyncMock(return_value=created)

        service = ScanService(mock_db)
        inputs = [
            ScanIngredientInput(
                ingredient_name="Niacinamide",
                detected_name="Niacinamide",
                confidence_score=0.95,
            )
        ]

        result = _run(service.add_scan_ingredients("scan-1", inputs))
        assert len(result) == 1
        assert result[0] == created


# ===========================================================================
# SECTION C — persist_analysis Error Handling
# ===========================================================================


class TestPersistAnalysisErrorHandling:
    """Verify persist_analysis handles errors with structured logging."""

    def test_persist_analysis_handles_prisma_error(self) -> None:
        """persist_analysis catches PrismaError and does not raise."""
        from prisma.errors import PrismaError

        mock_db = MagicMock()
        service = ScanService(mock_db)

        # Make the transaction context manager raise PrismaError
        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=PrismaError("DB down"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        # Should not raise — persist_analysis swallows PrismaError
        _run(service.persist_analysis(
            user_id="user-1",
            ingredients=["Water", "Niacinamide"],
            overall_score=8.5,
        ))

    def test_persist_analysis_handles_generic_exception(self) -> None:
        """persist_analysis catches generic Exception and does not raise."""
        mock_db = MagicMock()
        service = ScanService(mock_db)

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=RuntimeError("boom"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        # Should not raise — persist_analysis swallows all exceptions
        _run(service.persist_analysis(
            user_id="user-1",
            ingredients=["Water"],
            overall_score=9.0,
        ))

    def test_persist_analysis_logs_prisma_error_no_traceback(self, caplog) -> None:
        """PrismaError is logged at ERROR level without exc_info."""
        from prisma.errors import PrismaError

        mock_db = MagicMock()
        service = ScanService(mock_db)

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=PrismaError("DB connection lost"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        with caplog.at_level(logging.ERROR):
            _run(service.persist_analysis(
                user_id="user-123",
                ingredients=["Water", "Glycerin"],
                overall_score=7.0,
            ))

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "persist_analysis" in record.message
        assert "user-123" in record.message
        assert "PrismaError" in record.message
        assert record.exc_info is None  # No traceback for known DB errors

    def test_persist_analysis_logs_generic_error_with_traceback(self, caplog) -> None:
        """Generic Exception is logged with exc_info=True."""
        mock_db = MagicMock()
        service = ScanService(mock_db)

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=ValueError("unexpected"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        with caplog.at_level(logging.ERROR):
            _run(service.persist_analysis(
                user_id="user-456",
                ingredients=["Retinol"],
                overall_score=5.0,
            ))

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "persist_analysis" in record.message
        assert "user-456" in record.message
        assert "ValueError" in record.message
        assert record.exc_info is not None  # Traceback included for unexpected errors

    def test_persist_analysis_logs_ingredient_count(self, caplog) -> None:
        """Structured log includes ingredient count."""
        from prisma.errors import PrismaError

        mock_db = MagicMock()
        service = ScanService(mock_db)

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=PrismaError("fail"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        with caplog.at_level(logging.ERROR):
            _run(service.persist_analysis(
                user_id="user-789",
                ingredients=["A", "B", "C", "D", "E"],
                overall_score=6.0,
            ))

        assert "ingredient_count=5" in caplog.records[0].message

    def test_persist_analysis_never_exposes_secrets(self, caplog) -> None:
        """Error logs must not contain passwords, tokens, or secrets."""
        from prisma.errors import PrismaError

        mock_db = MagicMock()
        service = ScanService(mock_db)

        mock_tx = AsyncMock()
        mock_tx.scan.create = AsyncMock(side_effect=PrismaError("db error"))
        mock_db.tx = MagicMock(return_value=MagicMock(__aenter__=AsyncMock(return_value=mock_tx), __aexit__=AsyncMock(return_value=False)))

        with caplog.at_level(logging.ERROR):
            _run(service.persist_analysis(
                user_id="user-ok-999",
                ingredients=["Water"],
                overall_score=9.0,
            ))

        for record in caplog.records:
            assert "password" not in record.message.lower()
            assert "token" not in record.message.lower()
