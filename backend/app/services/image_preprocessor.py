"""
Image Preprocessing Service for OCR Optimization.

Handles image dimension & pixel validation, EXIF orientation correction,
resizing oversized images, contrast enhancement, and noise reduction.
"""

import os
import logging
from PIL import Image, ImageOps, ImageEnhance
from app.core.config import settings

logger = logging.getLogger(__name__)


class ImagePreprocessingError(ValueError):
    """Raised when an image fails preprocessing validation or processing limits."""
    pass


def preprocess_image(image_path: str) -> str:
    """Preprocess image before sending to OCR engine.

    Performs:
    1. Dimension & pixel count validation.
    2. EXIF orientation correction.
    3. Resizing of very large images.
    4. Contrast enhancement and conversion to RGB.

    Args:
        image_path: Path to local uploaded image file.

    Returns:
        Path to preprocessed image file (or original path if image format cannot be opened by PIL).

    Raises:
        ImagePreprocessingError: If image exceeds memory/dimension limits.
    """
    if not os.path.exists(image_path):
        raise ImagePreprocessingError(f"Image file not found: '{image_path}'")

    try:
        with Image.open(image_path) as img:
            # 1. Dimension and pixel limit checks
            width, height = img.size
            total_pixels = width * height

            if width > settings.MAX_IMAGE_WIDTH or height > settings.MAX_IMAGE_HEIGHT:
                raise ImagePreprocessingError(
                    f"Image dimensions ({width}x{height}) exceed maximum allowed "
                    f"limits ({settings.MAX_IMAGE_WIDTH}x{settings.MAX_IMAGE_HEIGHT})."
                )

            if total_pixels > settings.MAX_IMAGE_PIXELS:
                raise ImagePreprocessingError(
                    f"Image pixel count ({total_pixels}) exceeds maximum allowed "
                    f"limit of {settings.MAX_IMAGE_PIXELS} pixels."
                )

            # 2. Correct orientation based on EXIF tags
            try:
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.debug("EXIF transpose skipped: %s", e)

            # 3. Convert to RGB mode for consistent processing
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # 4. Resize if width/height exceeds optimal OCR target (2048px)
            max_target = 2048
            if img.width > max_target or img.height > max_target:
                img.thumbnail((max_target, max_target), Image.Resampling.LANCZOS)

            # 5. Enhance contrast for OCR readability
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.3)

            # 6. Save preprocessed image to temporary destination
            preprocessed_path = image_path + ".preprocessed.png"
            img.save(preprocessed_path, format="PNG")
            return preprocessed_path

    except ImagePreprocessingError:
        raise
    except Exception as exc:
        logger.warning("PIL image preprocessing skipped for %s (%s); returning original image_path.", image_path, exc)
        return image_path
