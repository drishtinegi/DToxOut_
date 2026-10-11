"""
Background OCR Job Tracking Service.

Provides an asynchronous job status abstraction for long-running OCR extractions.
Maintains job status (PENDING, PROCESSING, COMPLETED, FAILED) and state storage
while keeping mandatory user ingredient review intact before final safety analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import logging
from typing import Optional, Dict, Any
from app.schemas.scan import ImageProcessResponse

logger = logging.getLogger(__name__)


@dataclass
class OCRJobRecord:
    """In-memory or persistent background OCR job tracking record."""
    job_id: str
    upload_id: str
    status: str  # PENDING | PROCESSING | COMPLETED | FAILED
    created_at: datetime
    updated_at: datetime
    progress_pct: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error_detail: Optional[str] = None


# Global in-memory job registry for local deployment/test environments
_JOB_REGISTRY: Dict[str, OCRJobRecord] = {}


class OCRJobService:
    """Service to create, update, and track status of background OCR processing jobs."""

    def create_job(self, upload_id: str) -> OCRJobRecord:
        """Initialize a new background OCR job."""
        job_id = f"job-{uuid.uuid4()}"
        now = datetime.now(timezone.utc)
        record = OCRJobRecord(
            job_id=job_id,
            upload_id=upload_id,
            status="PENDING",
            created_at=now,
            updated_at=now,
            progress_pct=0.0,
        )
        _JOB_REGISTRY[job_id] = record
        logger.info("Initialized background OCR job_id=%s upload_id=%s", job_id, upload_id)
        return record

    def update_status(
        self,
        job_id: str,
        status: str,
        progress_pct: float = 0.0,
        result: Optional[Dict[str, Any]] = None,
        error_detail: Optional[str] = None,
    ) -> Optional[OCRJobRecord]:
        """Update status and progress of an existing background OCR job."""
        record = _JOB_REGISTRY.get(job_id)
        if not record:
            return None

        record.status = status
        record.progress_pct = progress_pct
        record.updated_at = datetime.now(timezone.utc)
        if result is not None:
            record.result = result
        if error_detail is not None:
            record.error_detail = error_detail

        logger.info("Updated background OCR job_id=%s status=%s progress=%.1f%%", job_id, status, progress_pct)
        return record

    def get_job(self, job_id: str) -> Optional[OCRJobRecord]:
        """Retrieve background OCR job record by job_id."""
        return _JOB_REGISTRY.get(job_id)
