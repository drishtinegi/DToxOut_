"""
Phase 2 Unit and Integration Tests: Import Pipeline & OCR Text Preparation.

Tests taxonomy extensions, batch import validation, dry-run, idempotency,
OCR cleaning utilities, parser confidence scoring, review_required flagging,
and POST /api/v1/scan/prepare-text endpoint.
"""

from typing import Dict
import pytest
from app.utils.ocr_cleaner import (
    clean_ocr_raw_text,
    fix_hyphenated_linebreaks,
    remove_percentages,
    strip_headers,
)
from app.services.ocr_adapter import OCRAdapter
from app.services.import_service import ImportService
from app.utils.ingredient_matcher import IngredientMatcher


class TestOCRCleaner:
    def test_strip_headers(self) -> None:
        raw = "Active Ingredients: Salicylic Acid (2%)\nInactive Ingredients: Water, Glycerin"
        cleaned, headers = strip_headers(raw)
        assert len(headers) == 2
        assert "Active Ingredients:" in headers
        assert "Inactive Ingredients:" in headers
        assert "Salicylic Acid" in cleaned

    def test_fix_hyphenated_linebreaks(self) -> None:
        raw = "salicylic-\nacid and niacin-\namide"
        fixed = fix_hyphenated_linebreaks(raw)
        assert "salicylic acid" in fixed
        assert "niacin amide" in fixed or "niacinamide" in fixed

    def test_remove_percentages(self) -> None:
        raw = "Salicylic Acid (5%), Niacinamide 10% w/w, Zinc PCA 0.5%"
        cleaned = remove_percentages(raw)
        assert "(5%)" not in cleaned
        assert "10% w/w" not in cleaned
        assert "0.5%" not in cleaned
        assert "Salicylic Acid" in cleaned

    def test_clean_bullets_and_noise(self) -> None:
        raw = "• Water, * Niacinamide , , Glycerin, Panthenol"
        cleaned_text, terms, warnings = clean_ocr_raw_text(raw)
        assert "Water" in terms
        assert "Niacinamide" in terms
        assert "Glycerin" in terms
        assert "Panthenol" in terms

    def test_full_clean_ocr_raw_text(self) -> None:
        raw = """
        INGREDIENTS:
        Water / Aqua (50%),
        Salicylic-
        Acid (2.0%),
        • Niacinamide (10.0% w/w),
        Glycerin
        """
        cleaned_text, terms, warnings = clean_ocr_raw_text(raw)
        assert len(warnings) >= 1
        assert "Water / Aqua" in terms or "Water" in terms
        assert any("Salicylic" in t for t in terms)
        assert "Niacinamide" in terms
        assert "Glycerin" in terms


class TestOCRAdapter:
    @pytest.mark.anyio
    async def test_ocr_adapter_high_confidence(self) -> None:
        # Pre-seed matcher with known terms
        matcher = IngredientMatcher()
        matcher.add_ingredient("Water", "Water", ["Water"])
        matcher.add_ingredient("Niacinamide", "Niacinamide", ["Niacinamide"])
        matcher.add_ingredient("Glycerin", "Glycerin", ["Glycerin"])

        adapter = OCRAdapter(matcher=matcher)
        raw_text = "Ingredients: Water, Niacinamide, Glycerin"
        res = await adapter.prepare_ocr_text(raw_text)

        assert res["parser_confidence"] >= 90.0
        assert res["review_required"] is False
        assert res["recognized_count"] == 3
        assert res["unknown_count"] == 0

    @pytest.mark.anyio
    async def test_ocr_adapter_low_confidence_and_review_required(self) -> None:
        matcher = IngredientMatcher()
        # Empty matcher -> all terms unknown
        adapter = OCRAdapter(matcher=matcher)
        raw_text = "Ingredients: UnknownChemicalA, UnknownExtractB, MysteriousLiquidC"
        res = await adapter.prepare_ocr_text(raw_text)

        assert res["parser_confidence"] == 0.0
        assert res["review_required"] is True
        assert res["unknown_count"] == 3
        assert len(res["warnings"]) >= 1

    @pytest.mark.anyio
    async def test_ocr_adapter_empty_input(self) -> None:
        adapter = OCRAdapter()
        res = await adapter.prepare_ocr_text("   ")
        assert res["candidate_count"] == 0
        assert res["parser_confidence"] == 0.0
        assert res["review_required"] is True


class TestImportServiceValidation:
    def test_manifest_validation_missing_fields(self) -> None:
        service = ImportService()
        errors1 = service.validate_manifest({})
        assert len(errors1) == 1
        assert "missing" in errors1[0].lower()

        errors2 = service.validate_manifest({"someKey": "someVal"})
        assert len(errors2) >= 3
        assert any("sourceOrganization" in e for e in errors2)
        assert any("sourceUrl" in e for e in errors2)

    def test_manifest_validation_invalid_url(self) -> None:
        service = ImportService()
        manifest = {
            "sourceOrganization": "CIR Panel",
            "sourceUrl": "invalid-url-string",
            "retrievedDate": "2026-01-01",
        }
        errors = service.validate_manifest(manifest)
        assert any("sourceUrl" in e for e in errors)

    def test_ingredient_validation_duplicate_inci(self) -> None:
        service = ImportService()
        seen = set()
        rec1 = {"inciName": "Niacinamide", "safetyRating": 9.0, "evidenceLevel": "HIGH"}
        rec2 = {"inciName": "niacinamide", "safetyRating": 8.5, "evidenceLevel": "HIGH"}

        err1, _ = service.validate_ingredient_record(rec1, 1, seen)
        err2, _ = service.validate_ingredient_record(rec2, 2, seen)

        assert len(err1) == 0
        assert len(err2) == 1
        assert "Duplicate INCI name" in err2[0]

    def test_ingredient_validation_invalid_enum(self) -> None:
        service = ImportService()
        seen = set()
        rec = {
            "inciName": "Panthenol",
            "safetyRating": 9.0,
            "evidenceLevel": "SUPER_HIGH",
            "sourceType": "MAGIC_SOURCE",
        }
        err, _ = service.validate_ingredient_record(rec, 1, seen)
        assert len(err) >= 2
        assert any("evidenceLevel" in e for e in err)
        assert any("sourceType" in e for e in err)

    @pytest.mark.anyio
    async def test_import_dry_run_mode(self) -> None:
        service = ImportService()
        payload = {
            "manifest": {
                "sourceOrganization": "Cosmetic Ingredient Review",
                "sourceUrl": "https://www.cir-safety.org",
                "retrievedDate": "2026-01-15",
                "defaultSourceType": "SCIENTIFIC_STUDY",
                "defaultVerificationStatus": "VERIFIED",
            },
            "ingredients": [
                {
                    "inciName": "Niacinamide",
                    "commonName": "Vitamin B3",
                    "description": "Skin barrier vitamin",
                    "function": "Skin conditioning",
                    "safetyRating": 9.0,
                    "evidenceLevel": "HIGH",
                },
                {
                    "inciName": "Panthenol",
                    "commonName": "Pro-Vitamin B5",
                    "description": "Soothing humectant",
                    "function": "Humectant",
                    "safetyRating": 9.5,
                    "evidenceLevel": "VERY_HIGH",
                },
            ],
        }

        summary = await service.import_batch(payload, dry_run=True)
        assert summary["total_records"] == 2
        assert summary["created_count"] == 2
        assert summary["error_count"] == 0
        assert summary["skipped_count"] == 0
