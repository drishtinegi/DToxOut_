"""
Scan Analysis API routes.

Exposes the ScanService through a single authenticated endpoint.
All business logic lives in ScanService — this module is a thin adapter
between HTTP and the service layer.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from prisma import Prisma
from prisma.models import User

from app.core.dependencies import get_current_user
from app.database import get_db
from app.middleware.rate_limiting import limiter
from app.schemas.scan import (
    ImageProcessRequest,
    ImageProcessResponse,
    ImageUploadResponse,
    OCRPrepareRequest,
    OCRPrepareResponse,
    ScanRequest,
    ScanResponse,
)
from app.services.scan_service import ScanService
from app.services.upload_service import save_uploaded_image
from app.services.ocr_provider import get_ocr_provider
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan", tags=["Scan"])


# ---------------------------------------------------------------------------
# Dependency: provide a ScanService wired to the current DB client
# ---------------------------------------------------------------------------


def _get_scan_service(db: Prisma = Depends(get_db)) -> ScanService:
    """Build a ScanService per request using the active DB client."""
    return ScanService(db)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/analyze",
    response_model=ScanResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_SCAN)
async def analyze_ingredients(
    request: Request,
    response: Response,
    payload: ScanRequest,
    current_user: User = Depends(get_current_user),
    service: ScanService = Depends(_get_scan_service),
) -> ScanResponse:
    """Analyze a list of cosmetic ingredients for safety information."""
    scan_result = await service.analyze_ingredients(
        payload.ingredients,
        selected_jurisdiction=payload.selected_jurisdiction,
    )

    logger.info("Analysis completed for user %s", current_user.id)

    await service.persist_analysis(
        user_id=current_user.id,
        ingredients=payload.ingredients,
        overall_score=scan_result.overall_score,
    )

    logger.debug("Persist completed for user %s", current_user.id)

    return scan_result


@router.post(
    "/prepare-text",
    response_model=OCRPrepareResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_SCAN)
async def prepare_ocr_text(
    request: Request,
    response: Response,
    payload: OCRPrepareRequest,
    current_user: User = Depends(get_current_user),
    db: Prisma = Depends(get_db),
) -> OCRPrepareResponse:
    """Prepares raw OCR text by cleaning formatting artifacts and matching terms."""
    from app.services.ocr_adapter import OCRAdapter

    adapter = OCRAdapter()
    result = await adapter.prepare_ocr_text(payload.raw_text, db=db)
    return OCRPrepareResponse(**result)


@router.post(
    "/upload-image",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.RATE_LIMIT_SCAN)
async def upload_image(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> ImageUploadResponse:
    """Upload an image file securely for OCR analysis.

    Validates format, magic bytes, and file size. Generates a safe server UUID.
    """
    res = await save_uploaded_image(file)
    return ImageUploadResponse(**res)


@router.post(
    "/process-image",
    response_model=ImageProcessResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(settings.RATE_LIMIT_SCAN)
async def process_image(
    request: Request,
    response: Response,
    payload: ImageProcessRequest,
    current_user: User = Depends(get_current_user),
    db: Prisma = Depends(get_db),
) -> ImageProcessResponse:
    """Process an uploaded image via OCR engine and prepare terms for user review.

    Does NOT run final safety analysis or persist scan history.
    Cleans up temporary uploaded image file after extraction if enabled.
    """
    import os
    from app.services.ocr_adapter import OCRAdapter
    from app.services.image_preprocessor import preprocess_image, ImagePreprocessingError
    from app.services.ocr_provider import get_ocr_provider, OCRProviderUnavailableError, OCRTimeoutError
    from app.services.upload_service import delete_upload_by_id

    # 1. Path traversal protection & file lookup
    clean_upload_id = os.path.basename(payload.upload_id).replace("..", "")
    target_path = None
    if os.path.exists(settings.UPLOAD_DIR):
        for f_name in os.listdir(settings.UPLOAD_DIR):
            if f_name.startswith(clean_upload_id):
                target_path = os.path.join(settings.UPLOAD_DIR, f_name)
                break

    if not target_path or not os.path.exists(target_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Uploaded image session '{payload.upload_id}' not found.",
        )

    preprocessed_path = None
    try:
        # 2. Image Preprocessing (orientation, dimension check, contrast enhancement)
        preprocessed_path = preprocess_image(target_path)

        # 3. Extract OCR text
        ocr_provider = get_ocr_provider()
        ocr_res = await ocr_provider.extract_text(preprocessed_path)

        # Fail clearly on empty or whitespace-only OCR text
        if not ocr_res.raw_text or not ocr_res.raw_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No readable ingredient text could be extracted from the uploaded image. Please try a clearer picture of the ingredient label.",
            )

        # 4. Clean and prepare terms via OCRAdapter
        adapter = OCRAdapter()
        parsed_res = await adapter.prepare_ocr_text(ocr_res.raw_text, db=db)

        # Calculate review triggers (low OCR conf, low parser conf, high unknown ratio, short terms)
        candidate_terms = parsed_res.get("candidate_terms", [])
        has_short_term = any(len(term.strip()) < 3 for term in candidate_terms)
        unknown_count = parsed_res.get("unknown_count", 0)
        total_count = max(len(candidate_terms), 1)
        high_unknown_ratio = (unknown_count / total_count) > 0.30

        review_required = (
            parsed_res.get("review_required", False)
            or (ocr_res.provider_confidence < settings.OCR_MIN_CONFIDENCE)
            or (parsed_res.get("parser_confidence", 0.0) < 75.0)
            or high_unknown_ratio
            or has_short_term
        )

        combined_warnings = list(dict.fromkeys(ocr_res.warnings + parsed_res.get("warnings", [])))
        if review_required and "User review recommended before running safety analysis." not in combined_warnings:
            combined_warnings.append("User review recommended before running safety analysis.")

        return ImageProcessResponse(
            upload_id=payload.upload_id,
            raw_text=ocr_res.raw_text,
            cleaned_text=parsed_res["cleaned_text"],
            candidate_terms=candidate_terms,
            match_details=parsed_res["match_details"],
            ocr_provider=ocr_res.provider_name,
            ocr_confidence=ocr_res.provider_confidence,
            parser_confidence=parsed_res["parser_confidence"],
            processing_duration_ms=ocr_res.processing_duration_ms,
            review_required=review_required,
            warnings=combined_warnings,
            recognized_count=parsed_res["recognized_count"],
            unknown_count=unknown_count,
        )

    except ImagePreprocessingError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Image preprocessing failed: {str(exc)}",
        ) from exc
    except OCRProviderUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR Provider Configuration Error: {str(exc)}",
        ) from exc
    except OCRTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"OCR processing timed out: {str(exc)}",
        ) from exc

    finally:
        # Clean up temporary preprocessed file
        if preprocessed_path and os.path.exists(preprocessed_path):
            try:
                os.remove(preprocessed_path)
            except Exception as e:
                logger.warning("Failed to remove preprocessed temp file %s: %s", preprocessed_path, e)

        # Clean up original upload file if configured
        if settings.DELETE_TEMP_UPLOADS:
            delete_upload_by_id(payload.upload_id)



