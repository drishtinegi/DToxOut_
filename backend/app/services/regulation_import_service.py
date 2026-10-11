"""
Regulatory Knowledge-Base Import Service.

Imports batch regulatory records (JSON/CSV) into the DToxOut Prisma database
with strict manifest validation, INCI exact-matching, idempotency, dry-run support,
and unmatched ingredient reporting.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from prisma import Prisma
from app.core.exceptions import DomainError


class ManifestValidationError(DomainError):
    """Raised when the regulatory import manifest is missing or invalid."""

    status_code = 400

    def __init__(self, detail: str = "Invalid regulatory manifest") -> None:
        super().__init__(detail)


class RegulationImportValidationError(DomainError):
    """Raised when regulatory import validation fails."""

    status_code = 422

    def __init__(self, detail: str = "Regulatory import validation failed") -> None:
        super().__init__(detail)


VALID_REGULATORY_STATUSES = {"APPROVED", "RESTRICTED", "BANNED", "PENDING_REVIEW"}
VALID_VERIFICATION_STATUSES = {"UNVERIFIED", "PENDING_REVIEW", "VERIFIED", "DEPRECATED"}
VALID_SOURCE_TYPES = {
    "REGULATORY_LIST",
    "SCIENTIFIC_STUDY",
    "VENDOR_SPEC",
    "COMMUNITY_REPORT",
    "INTERNAL_AUDIT",
}


class RegulationImportService:
    """Service to handle verified regulatory knowledge-base imports."""

    def __init__(self, db: Prisma) -> None:
        self._db = db

    def validate_manifest(self, manifest: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Validates that mandatory manifest fields exist and are well-formed.

        Required manifest fields:
        - sourceOrganization
        - sourceUrl
        - retrievedDate
        - defaultSourceType
        - defaultVerificationStatus
        - licenseNote
        """
        if not manifest or not isinstance(manifest, dict):
            raise ManifestValidationError(
                "Regulatory import requires a valid manifest object containing source provenance and licensing metadata."
            )

        required_fields = [
            "sourceOrganization",
            "sourceUrl",
            "retrievedDate",
            "defaultSourceType",
            "defaultVerificationStatus",
            "licenseNote",
        ]

        missing = [
            field
            for field in required_fields
            if field not in manifest or manifest[field] is None or str(manifest[field]).strip() == ""
        ]
        if missing:
            raise ManifestValidationError(
                f"Missing required manifest field(s): {', '.join(missing)}"
            )

        # Validate URL
        url = str(manifest["sourceUrl"]).strip()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
            raise ManifestValidationError(f"Invalid manifest sourceUrl: '{url}'")

        # Validate status enums in manifest
        source_type = str(manifest["defaultSourceType"]).upper()
        if source_type not in VALID_SOURCE_TYPES:
            raise ManifestValidationError(f"Invalid defaultSourceType in manifest: '{source_type}'")

        ver_status = str(manifest["defaultVerificationStatus"]).upper()
        if ver_status not in VALID_VERIFICATION_STATUSES:
            raise ManifestValidationError(f"Invalid defaultVerificationStatus in manifest: '{ver_status}'")

        return manifest

    def _parse_date(self, date_val: Any) -> Optional[datetime]:
        """Converts ISO date string or datetime to standard UTC datetime object."""
        if not date_val:
            return None
        if isinstance(date_val, datetime):
            return date_val
        val_str = str(date_val).strip()
        if not val_str:
            return None
        try:
            # Handle standard ISO strings like 2024-01-01 or 2024-01-01T00:00:00Z
            if val_str.endswith("Z"):
                val_str = val_str[:-1] + "+00:00"
            return datetime.fromisoformat(val_str)
        except ValueError:
            # Try YYYY-MM-DD format
            try:
                return datetime.strptime(val_str, "%Y-%m-%d")
            except ValueError:
                return None

    def _validate_record_url(self, url_str: Optional[str]) -> bool:
        if not url_str:
            return True
        u = str(url_str).strip()
        return u.startswith("http://") or u.startswith("https://") or u.startswith("file://")

    async def _build_inci_map(self) -> Dict[str, str]:
        """Builds exact lookup table: uppercase INCI name / alias -> ingredient ID."""
        inci_map: Dict[str, str] = {}

        # Fetch canonical INCI names
        ingredients = await self._db.ingredient.find_many()
        for ing in ingredients:
            inci_map[ing.inciName.strip().upper()] = ing.id

        # Fetch aliases
        aliases = await self._db.ingredientalias.find_many()
        for al in aliases:
            key = al.alias.strip().upper()
            if key not in inci_map:
                inci_map[key] = al.ingredientId

        return inci_map

    async def import_regulations(
        self,
        data_input: Union[str, bytes, List[Dict[str, Any]], Dict[str, Any]],
        manifest: Optional[Dict[str, Any]] = None,
        file_format: str = "json",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Executes verified batch regulatory import.

        Args:
            data_input: Raw JSON string/bytes, dict with manifest/data keys, list of dicts, or CSV text.
            manifest: Optional explicit manifest dictionary.
            file_format: 'json' or 'csv'.
            dry_run: If True, validates and previews import without persisting to DB.

        Returns:
            Dictionary containing metrics, unmatched names, rejected records, warnings, and manifest.
        """
        records: List[Dict[str, Any]] = []

        # Parse input payload & extract embedded manifest if present
        if isinstance(data_input, dict):
            if "manifest" in data_input and manifest is None:
                manifest = data_input["manifest"]
            if "data" in data_input:
                raw_data = data_input["data"]
                if isinstance(raw_data, list):
                    records = raw_data
                elif isinstance(raw_data, str):
                    records = json.loads(raw_data)
            elif "records" in data_input:
                records = data_input["records"]
        elif isinstance(data_input, (str, bytes)):
            content_str = data_input.decode("utf-8") if isinstance(data_input, bytes) else data_input
            content_str = content_str.strip()
            if file_format.lower() == "csv":
                reader = csv.DictReader(io.StringIO(content_str))
                records = [row for row in reader]
            else:
                parsed = json.loads(content_str)
                if isinstance(parsed, dict):
                    if "manifest" in parsed and manifest is None:
                        manifest = parsed["manifest"]
                    records = parsed.get("data", parsed.get("records", []))
                elif isinstance(parsed, list):
                    records = parsed
        elif isinstance(data_input, list):
            records = data_input

        # Validate manifest
        validated_manifest = self.validate_manifest(manifest)

        # Build INCI lookup map from database
        inci_map = await self._build_inci_map()

        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        warnings: List[str] = []
        rejected_records: List[Dict[str, Any]] = []
        unmatched_names: List[str] = []
        seen_unmatched = set()

        default_source_org = validated_manifest["sourceOrganization"]
        default_source_url = validated_manifest["sourceUrl"]
        retrieved_dt = self._parse_date(validated_manifest["retrievedDate"])
        default_source_type = str(validated_manifest["defaultSourceType"]).upper()
        default_ver_status = str(validated_manifest["defaultVerificationStatus"]).upper()

        for idx, raw_rec in enumerate(records, start=1):
            inci_name = (
                raw_rec.get("inciName")
                or raw_rec.get("inci_name")
                or raw_rec.get("ingredientName")
                or raw_rec.get("ingredient_name")
            )
            if not inci_name or not str(inci_name).strip():
                error_count += 1
                rejected_records.append(
                    {"row": idx, "record": raw_rec, "reason": "Missing INCI name"}
                )
                continue

            clean_inci = str(inci_name).strip().upper()

            # Exact INCI match check
            ingredient_id = inci_map.get(clean_inci)
            if not ingredient_id:
                # Log as unmatched for manual review - NEVER auto-create ingredient!
                if clean_inci not in seen_unmatched:
                    seen_unmatched.add(clean_inci)
                    unmatched_names.append(str(inci_name).strip())
                rejected_records.append(
                    {
                        "row": idx,
                        "record": raw_rec,
                        "reason": f"INCI name '{inci_name}' not matched in knowledge base",
                    }
                )
                continue

            country = (raw_rec.get("country") or raw_rec.get("country_code") or "").strip().upper()
            if not country:
                error_count += 1
                rejected_records.append(
                    {"row": idx, "record": raw_rec, "reason": "Missing country"}
                )
                continue

            jurisdiction = (raw_rec.get("jurisdiction") or country).strip().upper()

            reg_status_raw = (
                raw_rec.get("regulatoryStatus")
                or raw_rec.get("regulatory_status")
                or raw_rec.get("status")
                or ""
            ).strip().upper()

            if reg_status_raw not in VALID_REGULATORY_STATUSES:
                error_count += 1
                rejected_records.append(
                    {
                        "row": idx,
                        "record": raw_rec,
                        "reason": f"Invalid regulatoryStatus: '{reg_status_raw}'. Must be one of {sorted(VALID_REGULATORY_STATUSES)}",
                    }
                )
                continue

            source_url = raw_rec.get("sourceUrl") or raw_rec.get("source_url") or default_source_url
            if not self._validate_record_url(source_url):
                error_count += 1
                rejected_records.append(
                    {
                        "row": idx,
                        "record": raw_rec,
                        "reason": f"Invalid source URL format: '{source_url}'",
                    }
                )
                continue

            effective_date_raw = raw_rec.get("effectiveDate") or raw_rec.get("effective_date")
            effective_dt = self._parse_date(effective_date_raw)
            if effective_date_raw and not effective_dt:
                warnings.append(
                    f"Row {idx}: Invalid effectiveDate '{effective_date_raw}' could not be parsed."
                )

            restriction_details = (
                raw_rec.get("restrictionDetails")
                or raw_rec.get("restriction_details")
                or raw_rec.get("conditions")
                or f"Status: {reg_status_raw}"
            ).strip()

            product_category = (
                raw_rec.get("productCategory")
                or raw_rec.get("product_category")
                or raw_rec.get("category")
            )
            if product_category:
                product_category = str(product_category).strip()

            concentration_limit = (
                raw_rec.get("concentrationLimit")
                or raw_rec.get("concentration_limit")
                or raw_rec.get("maxConcentration")
                or raw_rec.get("max_concentration")
            )
            if concentration_limit:
                concentration_limit = str(concentration_limit).strip()

            source_org = raw_rec.get("sourceOrganization") or raw_rec.get("source_organization") or default_source_org
            source_doc_id = raw_rec.get("sourceDocumentId") or raw_rec.get("source_document_id")
            source_label = raw_rec.get("source") or f"{source_org} Regulation List"
            
            ver_status = (
                raw_rec.get("verificationStatus")
                or raw_rec.get("verification_status")
                or default_ver_status
            ).strip().upper()
            if ver_status not in VALID_VERIFICATION_STATUSES:
                ver_status = default_ver_status

            reviewer_notes = raw_rec.get("reviewerNotes") or raw_rec.get("reviewer_notes")

            # Check existing regulation for idempotency
            where_clause: Dict[str, Any] = {
                "ingredientId": ingredient_id,
                "country": country,
            }
            if jurisdiction:
                where_clause["jurisdiction"] = jurisdiction
            if product_category:
                where_clause["productCategory"] = product_category

            existing_reg = await self._db.regulation.find_first(where=where_clause)

            if existing_reg:
                # Check if values match exactly
                is_identical = (
                    existing_reg.regulatoryStatus == reg_status_raw
                    and existing_reg.restrictionDetails == restriction_details
                    and (existing_reg.concentrationLimit or None) == (concentration_limit or None)
                    and existing_reg.verificationStatus == ver_status
                )
                if is_identical:
                    skipped_count += 1
                else:
                    if not dry_run:
                        update_data: Dict[str, Any] = {
                            "regulatoryStatus": reg_status_raw,
                            "restrictionDetails": restriction_details,
                            "source": source_label,
                            "sourceOrganization": source_org,
                            "sourceUrl": source_url,
                            "verificationStatus": ver_status,
                        }
                        if retrieved_dt:
                            update_data["retrievedDate"] = retrieved_dt
                        if effective_dt:
                            update_data["effectiveDate"] = effective_dt
                        if concentration_limit:
                            update_data["concentrationLimit"] = concentration_limit
                        if source_doc_id:
                            update_data["sourceDocumentId"] = source_doc_id
                        if reviewer_notes:
                            update_data["reviewerNotes"] = reviewer_notes

                        await self._db.regulation.update(
                            where={"id": existing_reg.id}, data=update_data
                        )
                    updated_count += 1
            else:
                if not dry_run:
                    create_data: Dict[str, Any] = {
                        "ingredientId": ingredient_id,
                        "country": country,
                        "jurisdiction": jurisdiction,
                        "regulatoryStatus": reg_status_raw,
                        "restrictionDetails": restriction_details,
                        "source": source_label,
                        "sourceOrganization": source_org,
                        "sourceUrl": source_url,
                        "sourceType": default_source_type,
                        "verificationStatus": ver_status,
                    }
                    if retrieved_dt:
                        create_data["retrievedDate"] = retrieved_dt
                    if effective_dt:
                        create_data["effectiveDate"] = effective_dt
                    if concentration_limit:
                        create_data["concentrationLimit"] = concentration_limit
                    if product_category:
                        create_data["productCategory"] = product_category
                    if source_doc_id:
                        create_data["sourceDocumentId"] = source_doc_id
                    if reviewer_notes:
                        create_data["reviewerNotes"] = reviewer_notes

                    await self._db.regulation.create(data=create_data)
                created_count += 1

        return {
            "dry_run": dry_run,
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "unmatched_count": len(unmatched_names),
            "unmatched_names": unmatched_names,
            "error_count": error_count,
            "warnings": warnings,
            "rejected_records": rejected_records,
            "manifest": validated_manifest,
        }
