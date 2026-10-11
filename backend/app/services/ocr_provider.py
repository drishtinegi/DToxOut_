"""
Vendor-independent OCR Provider Abstraction Layer.

Provides a unified interface for extracting raw text from cosmetic ingredient label images.
Supports local Tesseract, PaddleOCR, and DevMock providers without silent fallbacks in production.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import os
import time
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRProviderUnavailableError(RuntimeError):
    """Raised when the configured OCR provider engine is unavailable or unconfigured."""
    pass


class OCRTimeoutError(RuntimeError):
    """Raised when OCR extraction exceeds the configured timeout."""
    pass


@dataclass
class OCRResult:
    """Standardized OCR extraction result."""
    raw_text: str
    provider_name: str
    provider_confidence: float
    warnings: list[str] = field(default_factory=list)
    processing_duration_ms: float = 0.0


class BaseOCRProvider(ABC):
    """Abstract interface for all OCR providers."""

    @abstractmethod
    async def extract_text(self, image_path: str) -> OCRResult:
        """Extract raw text from an image file path."""
        pass


class DevMockOCRProvider(BaseOCRProvider):
    """Deterministic development/test OCR provider."""

    async def extract_text(self, image_path: str) -> OCRResult:
        start_time = time.perf_counter()
        logger.info("Running DevMockOCRProvider on %s", image_path)
        
        filename = os.path.basename(image_path).lower()
        duration_ms = (time.perf_counter() - start_time) * 1000.0 + 12.5

        if "low_conf" in filename:
            return OCRResult(
                raw_text="INGRED1ENTS: Aqua, N1ac1nam1de (3%), Z1nc PCA, Xanthan Gum.",
                provider_name="DevMockOCRProvider",
                provider_confidence=0.45,
                warnings=["Low image resolution detected", "Blurry text area near border"],
                processing_duration_ms=round(duration_ms, 2),
            )
        elif "blurry" in filename or "empty" in filename:
            return OCRResult(
                raw_text="",
                provider_name="DevMockOCRProvider",
                provider_confidence=0.10,
                warnings=["No readable text could be recognized from the image."],
                processing_duration_ms=round(duration_ms, 2),
            )
        
        default_text = (
            "INGREDIENTS: Aqua / Water, Glycerin, Niacinamide, Zinc PCA, "
            "Dimethyl Isosorbide, Tamarindus Indica Seed Gum, Xanthan Gum, "
            "Isoceteth-10, Ethoxydiglycol, Phenoxyethanol, Chlorphenesin."
        )
        return OCRResult(
            raw_text=default_text,
            provider_name="DevMockOCRProvider",
            provider_confidence=0.95,
            warnings=[],
            processing_duration_ms=round(duration_ms, 2),
        )


class TesseractOCRProvider(BaseOCRProvider):
    """Local Tesseract OCR adapter."""

    def __init__(self):
        self.available = False
        self.error_msg = ""
        try:
            import pytesseract
            from PIL import Image
            self.pytesseract = pytesseract
            self.Image = Image
            
            # Check if tesseract executable binary is accessible
            tess_version = self.pytesseract.get_tesseract_version()
            self.available = True
            logger.info("Tesseract OCR initialized successfully (version: %s)", tess_version)
        except Exception as exc:
            self.available = False
            self.error_msg = str(exc)
            logger.warning("Tesseract OCR engine unavailable: %s", exc)

    async def extract_text(self, image_path: str) -> OCRResult:
        if not self.available:
            raise OCRProviderUnavailableError(
                f"Tesseract OCR provider configured ('{settings.OCR_PROVIDER}'), "
                f"but engine or pytesseract library is not available on server. Details: {self.error_msg}"
            )

        start_time = time.perf_counter()
        try:
            image = self.Image.open(image_path)
            
            # Run pytesseract with confidence extraction and timeout
            data = self.pytesseract.image_to_data(
                image,
                lang=settings.OCR_LANGUAGE,
                output_type=self.pytesseract.Output.DICT,
                timeout=settings.OCR_TIMEOUT_SECONDS,
            )

            words = []
            confidences = []
            for text, conf in zip(data.get("text", []), data.get("conf", [])):
                t_stripped = text.strip()
                if t_stripped and conf != -1:
                    words.append(t_stripped)
                    confidences.append(float(conf))

            raw_text = " ".join(words)
            avg_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            warnings = []
            if avg_confidence < settings.OCR_MIN_CONFIDENCE:
                warnings.append(
                    f"OCR extraction confidence ({avg_confidence:.2f}) is below minimum threshold ({settings.OCR_MIN_CONFIDENCE})."
                )

            return OCRResult(
                raw_text=raw_text,
                provider_name="TesseractOCRProvider",
                provider_confidence=round(avg_confidence, 2),
                warnings=warnings,
                processing_duration_ms=round(duration_ms, 2),
            )

        except RuntimeError as exc:
            if "timeout" in str(exc).lower():
                raise OCRTimeoutError(f"Tesseract OCR process timed out after {settings.OCR_TIMEOUT_SECONDS}s.") from exc
            raise OCRProviderUnavailableError(f"Tesseract OCR execution error: {str(exc)}") from exc
        except Exception as exc:
            logger.error("Tesseract extraction failed on %s: %s", image_path, exc)
            raise OCRProviderUnavailableError(f"Tesseract OCR extraction failed: {str(exc)}") from exc


class PaddleOCRProvider(BaseOCRProvider):
    """Local PaddleOCR adapter."""

    def __init__(self):
        self.available = False
        self.error_msg = ""
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(use_angle_cls=True, lang=settings.OCR_LANGUAGE)
            self.available = True
        except Exception as exc:
            self.available = False
            self.error_msg = str(exc)

    async def extract_text(self, image_path: str) -> OCRResult:
        if not self.available:
            raise OCRProviderUnavailableError(
                f"PaddleOCR provider configured ('{settings.OCR_PROVIDER}'), "
                f"but paddleocr library is not available on server. Details: {self.error_msg}"
            )

        start_time = time.perf_counter()
        try:
            result = self.ocr.ocr(image_path, cls=True)
            lines = []
            scores = []
            if result and result[0]:
                for line in result[0]:
                    text, score = line[1]
                    lines.append(text)
                    scores.append(score)

            raw_text = "\n".join(lines)
            avg_confidence = sum(scores) / len(scores) if scores else 0.0
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            return OCRResult(
                raw_text=raw_text,
                provider_name="PaddleOCRProvider",
                provider_confidence=round(avg_confidence, 2),
                warnings=[],
                processing_duration_ms=round(duration_ms, 2),
            )
        except Exception as exc:
            raise OCRProviderUnavailableError(f"PaddleOCR extraction failed: {str(exc)}") from exc


def get_ocr_provider(provider_type: Optional[str] = None) -> BaseOCRProvider:
    """Factory to retrieve configured OCR provider instance.

    Raises:
        OCRProviderUnavailableError: If specified provider is invalid or engine is missing.
    """
    provider_name = (provider_type or settings.OCR_PROVIDER).lower().strip()

    if provider_name == "mock":
        return DevMockOCRProvider()
    elif provider_name == "tesseract":
        return TesseractOCRProvider()
    elif provider_name == "paddle":
        return PaddleOCRProvider()
    else:
        raise OCRProviderUnavailableError(
            f"Unsupported or unrecognized OCR_PROVIDER setting '{provider_name}'. "
            f"Allowed options: 'mock', 'tesseract', 'paddle'."
        )
