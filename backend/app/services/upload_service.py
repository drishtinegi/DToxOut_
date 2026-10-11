"""
Secure Image Upload & Privacy Retention Service.

Handles image validation (MIME type, magic bytes, size limits),
safe UUID filename generation, storage in uploads directory,
and privacy retention cleanup of temporary files.
"""

import os
import time
import uuid
import logging
from typing import Dict, Any
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

MAGIC_BYTES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
}

MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def validate_image_header(content_header: bytes, content_type: str) -> bool:
    """Validate file content signature against magic bytes."""
    if content_type == "image/jpeg":
        return content_header.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content_header.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return content_header.startswith(b"RIFF") and b"WEBP" in content_header[8:16]
    return False


def sanitize_filename(filename: str) -> str:
    """Sanitize input filename to prevent path traversal attacks."""
    basename = os.path.basename(filename)
    clean = "".join(c for c in basename if c.isalnum() or c in (".", "_", "-"))
    return clean or "upload.bin"


async def save_uploaded_image(file: UploadFile) -> Dict[str, Any]:
    """Validate and save an uploaded image file safely.

    Raises:
        HTTPException 400: If file format is missing, unsupported MIME type, or invalid header magic bytes.
        HTTPException 413: If file exceeds maximum allowed size.
    """
    allowed_types = [t.strip().lower() for t in settings.ALLOWED_IMAGE_TYPES.split(",")]

    # 1. Content type check
    content_type = (file.content_type or "").lower().strip()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{content_type}'. Allowed formats: {', '.join(allowed_types)}.",
        )

    # 2. Read header bytes for signature validation & read full content for size check
    header_bytes = await file.read(512)
    if not header_bytes or not validate_image_header(header_bytes, content_type):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file signature or corrupted image format.",
        )

    # Read remaining file
    remaining_bytes = await file.read()
    total_bytes = header_bytes + remaining_bytes
    file_size = len(total_bytes)

    # 3. File size check
    if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size ({file_size} bytes) exceeds maximum limit of {max_mb:.1f}MB.",
        )

    # 4. Generate safe UUID filename (prevents directory traversal attacks)
    ext = MIME_EXTENSIONS.get(content_type, ".bin")
    upload_id = str(uuid.uuid4())
    safe_filename = f"{upload_id}{ext}"

    # Ensure uploads directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

    # Write file to disk
    with open(file_path, "wb") as f:
        f.write(total_bytes)

    logger.info("Saved uploaded file upload_id=%s size=%d bytes", upload_id, file_size)

    return {
        "upload_id": upload_id,
        "safe_filename": safe_filename,
        "media_type": content_type,
        "file_size": file_size,
        "status": "success",
    }


def delete_upload_by_id(upload_id: str) -> bool:
    """Safely delete uploaded image and associated preprocessed files by upload_id."""
    clean_id = os.path.basename(upload_id).replace("..", "")
    if not clean_id or not os.path.exists(settings.UPLOAD_DIR):
        return False

    deleted_any = False
    for filename in os.listdir(settings.UPLOAD_DIR):
        if filename.startswith(clean_id):
            full_path = os.path.join(settings.UPLOAD_DIR, filename)
            try:
                os.remove(full_path)
                deleted_any = True
                logger.info("Deleted upload file %s", filename)
            except Exception as exc:
                logger.warning("Failed to delete upload file %s: %s", filename, exc)
    return deleted_any


def cleanup_expired_uploads() -> int:
    """Delete uploads exceeding configured retention hours."""
    if not settings.RETAIN_UPLOADS:
        retention_sec = 0.0
    else:
        retention_sec = float(settings.UPLOAD_RETENTION_HOURS) * 3600.0

    if not os.path.exists(settings.UPLOAD_DIR):
        return 0

    now = time.time()
    cleaned_count = 0
    for filename in os.listdir(settings.UPLOAD_DIR):
        file_path = os.path.join(settings.UPLOAD_DIR, filename)
        try:
            mtime = os.path.getmtime(file_path)
            if (now - mtime) >= retention_sec:
                os.remove(file_path)
                cleaned_count += 1
        except Exception as exc:
            logger.warning("Error inspecting/removing file %s during retention cleanup: %s", filename, exc)
    return cleaned_count
