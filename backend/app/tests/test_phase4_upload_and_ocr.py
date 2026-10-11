"""
Phase 4 Unit Tests — Secure Image Upload, OCR Abstraction, Process-Image, Scan History & Cleanup.

Covers:
    A. Image upload validation (MIME, magic bytes, size limits, UUID filename generation)
    B. OCR Provider Abstraction Layer & DevMockOCRProvider
    C. Image-to-Review processing endpoint
    D. Temporary file cleanup behavior & security
    E. User scan history endpoints & isolation
"""

import os
import io
import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from prisma.models import User

from app.api.scan import router as scan_router
from app.api.scan_history import router as scan_history_router
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.exceptions import DomainError
from app.database import get_db
from app.services.upload_service import save_uploaded_image, validate_image_header
from app.services.ocr_provider import DevMockOCRProvider, get_ocr_provider, OCRResult


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Section A — Upload Service Unit Tests
# ---------------------------------------------------------------------------


class TestUploadServiceValidation:

    def test_magic_bytes_validation(self):
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        webp_bytes = b"RIFF\x00\x00\x00\x00WEBPVP8 "
        invalid_bytes = b"NOT_AN_IMAGE_FILE_DATA"

        assert validate_image_header(jpeg_bytes, "image/jpeg") is True
        assert validate_image_header(png_bytes, "image/png") is True
        assert validate_image_header(webp_bytes, "image/webp") is True
        assert validate_image_header(invalid_bytes, "image/jpeg") is False

    def test_save_uploaded_image_success(self, tmp_path):
        settings.UPLOAD_DIR = str(tmp_path)
        valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 100)

        file = UploadFile(filename="user_photo.jpg", file=io.BytesIO(valid_jpeg), headers={"content-type": "image/jpeg"})
        res = _run(save_uploaded_image(file))

        assert res["status"] == "success"
        assert res["media_type"] == "image/jpeg"
        assert res["file_size"] == len(valid_jpeg)
        assert res["safe_filename"].endswith(".jpg")
        assert os.path.exists(os.path.join(tmp_path, res["safe_filename"]))

    def test_save_uploaded_image_unsupported_mime(self):
        file = UploadFile(filename="malicious.exe", file=io.BytesIO(b"MZ..."), headers={"content-type": "application/x-msdownload"})
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _run(save_uploaded_image(file))
        assert exc_info.value.status_code == 400

    def test_save_uploaded_image_invalid_magic_bytes(self):
        file = UploadFile(filename="fake.jpg", file=io.BytesIO(b"PLAIN_TEXT_NOT_JPEG"), headers={"content-type": "image/jpeg"})
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _run(save_uploaded_image(file))
        assert exc_info.value.status_code == 400

    def test_save_uploaded_image_oversized(self):
        old_limit = settings.MAX_UPLOAD_SIZE_BYTES
        settings.MAX_UPLOAD_SIZE_BYTES = 100  # Set tiny limit
        try:
            valid_png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 200)
            file = UploadFile(filename="large.png", file=io.BytesIO(valid_png), headers={"content-type": "image/png"})
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                _run(save_uploaded_image(file))
            assert exc_info.value.status_code == 413
        finally:
            settings.MAX_UPLOAD_SIZE_BYTES = old_limit


# ---------------------------------------------------------------------------
# Section B — OCR Provider Tests
# ---------------------------------------------------------------------------


class TestOCRProvider:

    def test_dev_mock_ocr_provider_extraction(self):
        provider = DevMockOCRProvider()
        res = _run(provider.extract_text("label_sample.jpg"))

        assert isinstance(res, OCRResult)
        assert "INGREDIENTS:" in res.raw_text
        assert res.provider_confidence > 0.8
        assert res.provider_name == "DevMockOCRProvider"

    def test_dev_mock_ocr_provider_low_confidence(self):
        provider = DevMockOCRProvider()
        res = _run(provider.extract_text("low_conf_label.jpg"))

        assert res.provider_confidence < 0.6
        assert len(res.warnings) > 0


# ---------------------------------------------------------------------------
# Section C — Endpoint Integration Tests
# ---------------------------------------------------------------------------


async def _mock_get_current_user() -> User:
    user = MagicMock(spec=User)
    user.id = "00000000-0000-0000-0000-000000000001"
    user.email = "test@example.com"
    user.username = "testuser"
    user.role = "USER"
    return user


def _build_test_phase4_app(tmp_upload_dir):
    app = FastAPI(title="Phase 4 Test App")

    async def _domain_error_handler(request, exc: DomainError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.add_exception_handler(DomainError, _domain_error_handler)
    app.dependency_overrides[get_current_user] = _mock_get_current_user

    mock_db = MagicMock()
    mock_db.ingredient.find_many = AsyncMock(return_value=[])
    mock_db.alias.find_many = AsyncMock(return_value=[])

    async def _mock_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _mock_get_db

    app.include_router(scan_router, prefix="/api/v1")
    app.include_router(scan_history_router, prefix="/api/v1")
    return app


@pytest.fixture
def phase4_client(tmp_path):
    settings.UPLOAD_DIR = str(tmp_path)
    settings.OCR_PROVIDER = "mock"
    app = _build_test_phase4_app(tmp_path)
    return TestClient(app, raise_server_exceptions=False)


class TestPhase4Endpoints:

    def test_upload_image_endpoint_success(self, phase4_client):
        valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 100)
        res = phase4_client.post(
            "/api/v1/scan/upload-image",
            files={"file": ("label.jpg", valid_jpeg, "image/jpeg")},
        )
        assert res.status_code == 201
        body = res.json()
        assert "upload_id" in body
        assert body["media_type"] == "image/jpeg"
        assert body["status"] == "success"

    def test_upload_image_unauthenticated(self, tmp_path):
        app = FastAPI()
        app.include_router(scan_router, prefix="/api/v1")
        client = TestClient(app, raise_server_exceptions=False)

        valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 100)
        res = client.post(
            "/api/v1/scan/upload-image",
            files={"file": ("label.jpg", valid_jpeg, "image/jpeg")},
        )
        assert res.status_code in (401, 403)

    def test_process_image_endpoint_success_and_cleanup(self, phase4_client, tmp_path):
        # 1. Upload
        valid_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + (b"\x00" * 100)
        up_res = phase4_client.post(
            "/api/v1/scan/upload-image",
            files={"file": ("label.jpg", valid_jpeg, "image/jpeg")},
        )
        upload_id = up_res.json()["upload_id"]

        # Verify file exists before process
        files_before = os.listdir(tmp_path)
        assert len(files_before) == 1

        # 2. Process
        proc_res = phase4_client.post(
            "/api/v1/scan/process-image",
            json={"upload_id": upload_id},
        )
        assert proc_res.status_code == 200
        body = proc_res.json()
        assert body["upload_id"] == upload_id
        assert len(body["candidate_terms"]) > 0
        assert "raw_text" in body

        # 3. Verify file deleted after process (DELETE_TEMP_UPLOADS=True)
        files_after = os.listdir(tmp_path)
        assert len(files_after) == 0

    def test_process_image_nonexistent_upload_id(self, phase4_client):
        res = phase4_client.post(
            "/api/v1/scan/process-image",
            json={"upload_id": "nonexistent-uuid-123"},
        )
        assert res.status_code == 404
