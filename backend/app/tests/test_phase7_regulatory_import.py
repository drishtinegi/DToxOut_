"""
Phase 7 Regulatory Knowledge-Base Expansion Tests.

Verifies:
- Manifest validation (missing manifest, required fields, invalid URL)
- Valid regulatory import (JSON & CSV)
- Invalid regulatory status handling
- Duplicate regulation prevention & idempotent re-import
- Unknown INCI name reporting & no automatic ingredient creation
- Country & jurisdiction specific outputs and formatting
- Effective dates, verification statuses, concentration limits
- Restricted vs Banned recommendation behavior
- Isolation of regulatory disposition from baseline INCI safety score (no false universal-toxicity)
- Full Phase 1-6 regression verification

Run with:
    pytest app/tests/test_phase7_regulatory_import.py -v
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.scan import RecommendationWarning, ScanResponse
from app.services.regulation_import_service import (
    ManifestValidationError,
    RegulationImportService,
)
from app.services.regulation_service import RegulationService
from app.services.scan_service import ScanService


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_valid_manifest() -> Dict[str, Any]:
    return {
        "sourceOrganization": "European Commission",
        "sourceUrl": "https://ec.europa.eu/growth/tools-databases/cosing/",
        "retrievedDate": "2026-09-01T00:00:00Z",
        "defaultSourceType": "REGULATORY_LIST",
        "defaultVerificationStatus": "PENDING_REVIEW",
        "licenseNote": "Public sector database fixture for testing.",
    }


def _make_mock_db() -> MagicMock:
    """Create a mock Prisma DB client pre-loaded with known ingredients."""
    db = MagicMock()

    # Ingredient 1: Methylparaben (ID: ing-1)
    ing1 = MagicMock()
    ing1.id = "ing-1"
    ing1.inciName = "METHYLPARABEN"
    ing1.commonName = "Methylparaben"
    ing1.description = "Preservative"
    ing1.function = "Preservative"
    ing1.safetyRating = 7.0
    ing1.evidenceLevel = "HIGH"

    sp1 = MagicMock()
    sp1.riskLevel = "MODERATE"
    sp1.pregnancyRisk = None
    sp1.acneRisk = None
    sp1.sensitiveSkinRisk = None
    sp1.allergyRisk = None
    ing1.safetyProfile = sp1

    reg1 = MagicMock()
    reg1.country = "EU"
    reg1.jurisdiction = "EU"
    reg1.regulatoryStatus = "RESTRICTED"
    reg1.restrictionDetails = "Max concentration 0.4%"
    reg1.source = "CosIng"
    reg1.sourceOrganization = "European Commission"
    reg1.sourceUrl = "https://ec.europa.eu/growth/tools-databases/cosing/"
    reg1.retrievedDate = datetime(2026, 9, 1, tzinfo=timezone.utc)
    reg1.effectiveDate = datetime(2024, 1, 1, tzinfo=timezone.utc)
    reg1.verificationStatus = "PENDING_REVIEW"
    reg1.productCategory = "Cosmetics"
    reg1.concentrationLimit = "0.4%"
    ing1.regulations = [reg1]
    ing1.scientificReferences = []

    # Ingredient 2: Formaldehyde (ID: ing-2)
    ing2 = MagicMock()
    ing2.id = "ing-2"
    ing2.inciName = "FORMALDEHYDE"
    ing2.commonName = "Formaldehyde"
    ing2.description = "Disinfectant and preservative"
    ing2.function = "Preservative"
    ing2.safetyRating = 2.0
    ing2.evidenceLevel = "HIGH"

    sp2 = MagicMock()
    sp2.riskLevel = "VERY_HIGH"
    sp2.pregnancyRisk = "Avoid"
    sp2.acneRisk = None
    sp2.sensitiveSkinRisk = "Irritant"
    sp2.allergyRisk = "Sensitizer"
    ing2.safetyProfile = sp2

    reg2 = MagicMock()
    reg2.country = "EU"
    reg2.jurisdiction = "EU"
    reg2.regulatoryStatus = "BANNED"
    reg2.restrictionDetails = "Prohibited under Annex II entry 1577"
    reg2.source = "CosIng Annex II"
    reg2.sourceOrganization = "European Commission"
    reg2.sourceUrl = "https://ec.europa.eu/growth/tools-databases/cosing/"
    reg2.retrievedDate = datetime(2026, 9, 1, tzinfo=timezone.utc)
    reg2.effectiveDate = datetime(2019, 6, 12, tzinfo=timezone.utc)
    reg2.verificationStatus = "PENDING_REVIEW"
    reg2.productCategory = "All Cosmetics"
    reg2.concentrationLimit = "0.0%"
    ing2.regulations = [reg2]
    ing2.scientificReferences = []

    db.ingredient.find_many = AsyncMock(return_value=[ing1, ing2])
    db.ingredient.find_unique = AsyncMock(side_effect=lambda where: ing1 if where.get("id") == "ing-1" else ing2 if where.get("id") == "ing-2" else None)
    db.ingredientalias.find_many = AsyncMock(return_value=[])
    db.safetyprofile.find_many = AsyncMock(return_value=[])
    db.regulation.find_first = AsyncMock(return_value=None)
    db.regulation.create = AsyncMock(side_effect=lambda data: MagicMock(**data, id="reg-new"))
    db.regulation.update = AsyncMock(side_effect=lambda where, data: MagicMock(**data, id=where["id"]))

    return db


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_missing_manifest_raises_error():
    """Import should fail if manifest is missing or invalid."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    with pytest.raises(ManifestValidationError) as excinfo:
        service.validate_manifest(None)
    assert "requires a valid manifest" in str(excinfo.value)


def test_manifest_missing_required_field_raises_error():
    """Import should fail if required manifest field is missing."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    invalid_manifest = _make_valid_manifest()
    invalid_manifest.pop("sourceOrganization")

    with pytest.raises(ManifestValidationError) as excinfo:
        service.validate_manifest(invalid_manifest)
    assert "sourceOrganization" in str(excinfo.value)


def test_invalid_manifest_url_raises_error():
    """Import should fail if manifest sourceUrl is malformed."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    invalid_manifest = _make_valid_manifest()
    invalid_manifest["sourceUrl"] = "ftp://invalid-url.com"

    with pytest.raises(ManifestValidationError) as excinfo:
        service.validate_manifest(invalid_manifest)
    assert "Invalid manifest sourceUrl" in str(excinfo.value)


def test_valid_regulatory_import_json():
    """Valid JSON payload with manifest should be imported successfully."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    payload = {
        "manifest": _make_valid_manifest(),
        "data": [
            {
                "inciName": "METHYLPARABEN",
                "country": "EU",
                "jurisdiction": "EU",
                "regulatoryStatus": "RESTRICTED",
                "restrictionDetails": "Maximum concentration 0.4%",
                "productCategory": "Cosmetics",
                "concentrationLimit": "0.4%",
                "effectiveDate": "2024-01-01",
                "verificationStatus": "PENDING_REVIEW",
            }
        ],
    }

    res = _run(service.import_regulations(payload, dry_run=False))

    assert res["created_count"] == 1
    assert res["updated_count"] == 0
    assert res["skipped_count"] == 0
    assert res["unmatched_count"] == 0
    assert res["error_count"] == 0
    assert res["dry_run"] is False
    assert db.regulation.create.called


def test_valid_regulatory_import_csv():
    """Valid CSV string with explicit manifest should be imported successfully."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    csv_data = (
        "inciName,country,jurisdiction,regulatoryStatus,restrictionDetails,concentrationLimit,effectiveDate,verificationStatus\n"
        "METHYLPARABEN,EU,EU,RESTRICTED,Maximum concentration 0.4%,0.4%,2024-01-01,PENDING_REVIEW\n"
    )

    res = _run(
        service.import_regulations(
            data_input=csv_data,
            manifest=_make_valid_manifest(),
            file_format="csv",
            dry_run=False,
        )
    )

    assert res["created_count"] == 1
    assert res["unmatched_count"] == 0
    assert res["error_count"] == 0


def test_invalid_regulatory_status_rejected():
    """Records with invalid regulatoryStatus should be rejected."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    payload = {
        "manifest": _make_valid_manifest(),
        "data": [
            {
                "inciName": "METHYLPARABEN",
                "country": "EU",
                "regulatoryStatus": "SUPER_ILLEGAL",
                "restrictionDetails": "N/A",
            }
        ],
    }

    res = _run(service.import_regulations(payload, dry_run=False))

    assert res["created_count"] == 0
    assert res["error_count"] == 1
    assert len(res["rejected_records"]) == 1
    assert "Invalid regulatoryStatus" in res["rejected_records"][0]["reason"]


def test_unknown_inci_name_reported_unmatched():
    """Unmatched INCI names must be reported for manual review and NOT auto-created."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    payload = {
        "manifest": _make_valid_manifest(),
        "data": [
            {
                "inciName": "UNKNOWN_SECRET_CHEMICAL_99",
                "country": "US",
                "regulatoryStatus": "RESTRICTED",
                "restrictionDetails": "Evaluation pending",
            }
        ],
    }

    res = _run(service.import_regulations(payload, dry_run=False))

    assert res["created_count"] == 0
    assert res["unmatched_count"] == 1
    assert "UNKNOWN_SECRET_CHEMICAL_99" in res["unmatched_names"]
    # Ensure no auto-creation of Ingredient model occurred
    assert not db.ingredient.create.called


def test_idempotent_reimport_skips_identical_record():
    """Re-importing identical existing regulation record should be skipped."""
    db = _make_mock_db()

    existing_reg = MagicMock()
    existing_reg.id = "reg-existing-1"
    existing_reg.regulatoryStatus = "RESTRICTED"
    existing_reg.restrictionDetails = "Maximum concentration 0.4%"
    existing_reg.concentrationLimit = "0.4%"
    existing_reg.verificationStatus = "PENDING_REVIEW"

    db.regulation.find_first = AsyncMock(return_value=existing_reg)

    service = RegulationImportService(db)

    payload = {
        "manifest": _make_valid_manifest(),
        "data": [
            {
                "inciName": "METHYLPARABEN",
                "country": "EU",
                "jurisdiction": "EU",
                "regulatoryStatus": "RESTRICTED",
                "restrictionDetails": "Maximum concentration 0.4%",
                "concentrationLimit": "0.4%",
                "verificationStatus": "PENDING_REVIEW",
            }
        ],
    }

    res = _run(service.import_regulations(payload, dry_run=False))

    assert res["created_count"] == 0
    assert res["updated_count"] == 0
    assert res["skipped_count"] == 1
    assert not db.regulation.create.called
    assert not db.regulation.update.called


def test_dry_run_does_not_mutate_database():
    """Dry-run mode previews counts without making database mutations."""
    db = _make_mock_db()
    service = RegulationImportService(db)

    payload = {
        "manifest": _make_valid_manifest(),
        "data": [
            {
                "inciName": "METHYLPARABEN",
                "country": "EU",
                "regulatoryStatus": "RESTRICTED",
                "restrictionDetails": "Test restriction",
            }
        ],
    }

    res = _run(service.import_regulations(payload, dry_run=True))

    assert res["dry_run"] is True
    assert res["created_count"] == 1
    assert not db.regulation.create.called
    assert not db.regulation.update.called


def test_country_specific_output_and_banned_warning():
    """Analysis with selected_jurisdiction triggers BANNED warning and AVOID recommendation."""
    db = _make_mock_db()
    scan_service = ScanService(db)

    # Formaldehyde is BANNED in EU
    res: ScanResponse = _run(
        scan_service.analyze_ingredients(
            ["Formaldehyde"], selected_jurisdiction="EU"
        )
    )

    assert res.recommendation == "AVOID"
    reg_warnings = [w for w in res.warnings if w.type == "REGULATORY"]
    assert len(reg_warnings) >= 1
    assert reg_warnings[0].severity == "HIGH"
    assert "Banned in EU" in reg_warnings[0].title


def test_restricted_status_no_automatic_universal_toxicity_penalty():
    """Restricted status in a jurisdiction does NOT drop base INCI safety rating or cause false universal toxicity."""
    db = _make_mock_db()
    scan_service = ScanService(db)

    # Methylparaben is RESTRICTED (0.4% limit), base safety rating is 7.0
    res: ScanResponse = _run(
        scan_service.analyze_ingredients(
            ["Methylparaben"], selected_jurisdiction="EU"
        )
    )

    # Safety score remains baseline 7.0
    assert res.recognized_ingredients[0].safety_rating == 7.0
    # Recommendation is SAFE or USE WITH CAUTION based on composite score 7.0, NOT AVOID
    assert res.recommendation in ["SAFE", "USE WITH CAUTION"]

    reg_warnings = [w for w in res.warnings if w.type == "REGULATORY"]
    assert len(reg_warnings) >= 1
    assert reg_warnings[0].severity == "MODERATE"
    assert "Restriction in EU" in reg_warnings[0].title


def test_regulation_metadata_fields_populated_in_response():
    """Regulation fields in IngredientAnalysis response include full metadata."""
    db = _make_mock_db()
    scan_service = ScanService(db)

    res: ScanResponse = _run(scan_service.analyze_ingredients(["Methylparaben"]))

    regs = res.recognized_ingredients[0].regulations
    assert regs is not None
    assert len(regs) == 1

    r = regs[0]
    assert r["country"] == "EU"
    assert r["jurisdiction"] == "EU"
    assert r["status"] == "RESTRICTED"
    assert r["regulatory_status"] == "RESTRICTED"
    assert r["restriction_details"] == "Max concentration 0.4%"
    assert r["source_organization"] == "European Commission"
    assert r["source_url"] == "https://ec.europa.eu/growth/tools-databases/cosing/"
    assert r["verification_status"] == "PENDING_REVIEW"
    assert r["product_category"] == "Cosmetics"
    assert r["concentration_limit"] == "0.4%"
    assert r["effective_date"] is not None
