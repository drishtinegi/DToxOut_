"""
Verified Batch Ingredient Import Pipeline Service.

Parses CSV/JSON input with manifest metadata, validates records, supports dry-run mode,
performs idempotent upserts, and returns structured summary metrics.
"""

from datetime import datetime
import json
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from prisma import Prisma

from app.utils.ingredient_matcher import normalize_ingredient_name

VALID_SOURCE_TYPES = {
    "REGULATORY_LIST",
    "SCIENTIFIC_STUDY",
    "VENDOR_SPEC",
    "COMMUNITY_REPORT",
    "INTERNAL_AUDIT",
}

VALID_VERIFICATION_STATUSES = {
    "UNVERIFIED",
    "PENDING_REVIEW",
    "VERIFIED",
    "DEPRECATED",
}

VALID_EVIDENCE_LEVELS = {"LOW", "MODERATE", "HIGH", "VERY_HIGH"}
VALID_RISK_LEVELS = {"LOW", "MODERATE", "HIGH", "VERY_HIGH"}
VALID_REGULATORY_STATUSES = {"APPROVED", "RESTRICTED", "BANNED", "PENDING_REVIEW"}

URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


def validate_url(url: Optional[str]) -> bool:
    if not url:
        return True
    return bool(URL_REGEX.match(url.strip()))


class ImportService:
    """
    Service for executing verified batch ingredient imports.
    """

    def __init__(self, db: Optional[Prisma] = None) -> None:
        self.db = db

    def validate_manifest(self, manifest: Dict[str, Any]) -> List[str]:
        """
        Validates import manifest header.
        Returns a list of error strings if invalid.
        """
        errors = []
        if not manifest:
            return ["Import manifest block is missing."]

        org = manifest.get("sourceOrganization")
        if not org or not isinstance(org, str) or not org.strip():
            errors.append("Manifest missing required 'sourceOrganization'.")

        url = manifest.get("sourceUrl")
        if not url or not isinstance(url, str) or not validate_url(url):
            errors.append("Manifest missing or invalid 'sourceUrl' (must be valid HTTP/HTTPS URL).")

        retrieved = manifest.get("retrievedDate")
        if not retrieved or not isinstance(retrieved, str):
            errors.append("Manifest missing required 'retrievedDate' (ISO timestamp or YYYY-MM-DD string).")

        source_type = manifest.get("defaultSourceType", "INTERNAL_AUDIT")
        if source_type not in VALID_SOURCE_TYPES:
            errors.append(
                f"Invalid manifest defaultSourceType '{source_type}'. Must be one of: {', '.join(sorted(VALID_SOURCE_TYPES))}"
            )

        verification_status = manifest.get("defaultVerificationStatus", "UNVERIFIED")
        if verification_status not in VALID_VERIFICATION_STATUSES:
            errors.append(
                f"Invalid manifest defaultVerificationStatus '{verification_status}'. Must be one of: {', '.join(sorted(VALID_VERIFICATION_STATUSES))}"
            )

        return errors

    def validate_ingredient_record(
        self,
        record: Dict[str, Any],
        index: int,
        seen_incis: set
    ) -> Tuple[List[str], List[str]]:
        """
        Validates individual ingredient record.
        Returns (errors, warnings).
        """
        errors = []
        warnings = []

        inci_name = record.get("inciName") or record.get("inci_name")
        if not inci_name or not isinstance(inci_name, str) or not inci_name.strip():
            errors.append(f"Record #{index}: Missing or invalid 'inciName'.")
            return errors, warnings

        norm_inci = normalize_ingredient_name(inci_name)
        if norm_inci in seen_incis:
            errors.append(f"Record #{index}: Duplicate INCI name '{inci_name}' in import batch.")
        else:
            seen_incis.add(norm_inci)

        safety_rating = record.get("safetyRating") if "safetyRating" in record else record.get("safety_rating")
        if safety_rating is None:
            errors.append(f"Record #{index} ({inci_name}): Missing required 'safetyRating'.")
        else:
            try:
                rating_val = float(safety_rating)
                if not (0.0 <= rating_val <= 10.0):
                    errors.append(f"Record #{index} ({inci_name}): 'safetyRating' must be between 0.0 and 10.0.")
            except (ValueError, TypeError):
                errors.append(f"Record #{index} ({inci_name}): 'safetyRating' must be a numeric value.")

        evidence_level = record.get("evidenceLevel") or record.get("evidence_level")
        if not evidence_level or evidence_level not in VALID_EVIDENCE_LEVELS:
            errors.append(
                f"Record #{index} ({inci_name}): Missing or invalid 'evidenceLevel'. Must be one of: {', '.join(sorted(VALID_EVIDENCE_LEVELS))}"
            )

        # Check provenance overrides if present
        source_url = record.get("sourceUrl")
        if source_url and not validate_url(source_url):
            errors.append(f"Record #{index} ({inci_name}): Invalid 'sourceUrl' format.")

        source_type = record.get("sourceType")
        if source_type and source_type not in VALID_SOURCE_TYPES:
            errors.append(f"Record #{index} ({inci_name}): Invalid 'sourceType' '{source_type}'.")

        ver_status = record.get("verificationStatus")
        if ver_status and ver_status not in VALID_VERIFICATION_STATUSES:
            errors.append(f"Record #{index} ({inci_name}): Invalid 'verificationStatus' '{ver_status}'.")

        # Validate optional safety profile
        sp = record.get("safetyProfile") or record.get("safety_profile")
        if sp and isinstance(sp, dict):
            risk_level = sp.get("riskLevel") or sp.get("risk_level")
            if risk_level and risk_level not in VALID_RISK_LEVELS:
                errors.append(f"Record #{index} ({inci_name}): Invalid safetyProfile riskLevel '{risk_level}'.")

        return errors, warnings

    async def import_batch(
        self,
        payload: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Processes batch ingredient import payload.

        Payload structure:
        {
            "manifest": {
                "sourceOrganization": "CIR Expert Panel",
                "sourceUrl": "https://www.cir-safety.org",
                "retrievedDate": "2026-01-15",
                "defaultSourceType": "SCIENTIFIC_STUDY",
                "defaultVerificationStatus": "VERIFIED"
            },
            "ingredients": [ ... ]
        }
        """
        manifest = payload.get("manifest", {})
        ingredients = payload.get("ingredients", [])

        manifest_errors = self.validate_manifest(manifest)
        if manifest_errors:
            return {
                "total_records": len(ingredients),
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": len(ingredients),
                "error_count": len(manifest_errors),
                "errors": manifest_errors,
                "warnings": [],
                "matched_inci_terms": [],
            }

        all_errors = []
        all_warnings = []
        seen_incis = set()

        for idx, rec in enumerate(ingredients, start=1):
            rec_errors, rec_warnings = self.validate_ingredient_record(rec, idx, seen_incis)
            all_errors.extend(rec_errors)
            all_warnings.extend(rec_warnings)

        if all_errors or dry_run:
            # In dry-run or validation failure mode, calculate stats without writing
            return {
                "total_records": len(ingredients),
                "created_count": 0 if all_errors else len(ingredients),
                "updated_count": 0,
                "skipped_count": len(ingredients) if all_errors else 0,
                "error_count": len(all_errors),
                "errors": all_errors,
                "warnings": all_warnings,
                "matched_inci_terms": [rec.get("inciName") for rec in ingredients if rec.get("inciName")],
            }

        # Live import mode with Prisma DB
        if self.db is None:
            return {
                "total_records": len(ingredients),
                "created_count": 0,
                "updated_count": 0,
                "skipped_count": len(ingredients),
                "error_count": 1,
                "errors": ["Database connection instance not provided to ImportService."],
                "warnings": all_warnings,
                "matched_inci_terms": [],
            }

        created_count = 0
        updated_count = 0
        matched_inci_terms = []

        manifest_org = manifest.get("sourceOrganization")
        manifest_url = manifest.get("sourceUrl")
        manifest_retrieved_str = manifest.get("retrievedDate")
        manifest_source_type = manifest.get("defaultSourceType", "INTERNAL_AUDIT")
        manifest_ver_status = manifest.get("defaultVerificationStatus", "UNVERIFIED")

        try:
            retrieved_dt = datetime.fromisoformat(manifest_retrieved_str.replace("Z", "+00:00"))
        except Exception:
            retrieved_dt = datetime.utcnow()

        for rec in ingredients:
            inci_name = rec.get("inciName") or rec.get("inci_name")
            matched_inci_terms.append(inci_name)

            existing = await self.db.ingredient.find_unique(where={"inciName": inci_name})

            category_id = None
            category_name = rec.get("categoryName") or rec.get("category_name")
            if category_name:
                cat_record = await self.db.ingredientcategory.find_unique(where={"name": category_name})
                if not cat_record:
                    cat_record = await self.db.ingredientcategory.create(
                        data={"name": category_name, "description": f"Imported category {category_name}"}
                    )
                category_id = cat_record.id

            data_fields = {
                "inciName": inci_name,
                "commonName": rec.get("commonName") or rec.get("common_name"),
                "description": rec.get("description", f"Imported entry for {inci_name}"),
                "function": rec.get("function", "Cosmetic Ingredient"),
                "safetyRating": float(rec.get("safetyRating", rec.get("safety_rating", 5.0))),
                "evidenceLevel": rec.get("evidenceLevel", rec.get("evidence_level", "MODERATE")),
                "sourceOrganization": rec.get("sourceOrganization", manifest_org),
                "sourceUrl": rec.get("sourceUrl", manifest_url),
                "retrievedDate": retrieved_dt,
                "sourceType": rec.get("sourceType", manifest_source_type),
                "verificationStatus": rec.get("verificationStatus", manifest_ver_status),
                "reviewerNotes": rec.get("reviewerNotes"),
            }

            if category_id:
                data_fields["categoryId"] = category_id

            if existing:
                # Update existing ingredient
                updated_ingredient = await self.db.ingredient.update(
                    where={"id": existing.id},
                    data=data_fields
                )
                updated_count += 1
                ingredient_id = updated_ingredient.id
            else:
                # Create new ingredient
                new_ingredient = await self.db.ingredient.create(data=data_fields)
                created_count += 1
                ingredient_id = new_ingredient.id

            # Handle aliases
            aliases = rec.get("aliases", [])
            for alias_name in aliases:
                if isinstance(alias_name, str) and alias_name.strip():
                    clean_alias = alias_name.strip()
                    existing_alias = await self.db.ingredientalias.find_first(
                        where={"ingredientId": ingredient_id, "alias": clean_alias}
                    )
                    if not existing_alias:
                        await self.db.ingredientalias.create(
                            data={
                                "ingredientId": ingredient_id,
                                "alias": clean_alias,
                                "sourceOrganization": manifest_org,
                                "sourceUrl": manifest_url,
                                "sourceType": manifest_source_type,
                                "verificationStatus": manifest_ver_status,
                            }
                        )

            # Handle safety profile
            sp_data = rec.get("safetyProfile") or rec.get("safety_profile")
            if sp_data and isinstance(sp_data, dict):
                existing_sp = await self.db.safetyprofile.find_unique(where={"ingredientId": ingredient_id})
                sp_fields = {
                    "riskLevel": sp_data.get("riskLevel", sp_data.get("risk_level", "LOW")),
                    "allergyRisk": sp_data.get("allergyRisk", sp_data.get("allergy_risk", "Low")),
                    "pregnancyRisk": sp_data.get("pregnancyRisk", sp_data.get("pregnancy_risk", "Low")),
                    "acneRisk": sp_data.get("acneRisk", sp_data.get("acne_risk", "Low")),
                    "sensitiveSkinRisk": sp_data.get("sensitiveSkinRisk", sp_data.get("sensitive_skin_risk", "Low")),
                    "explanation": sp_data.get("explanation", "Safety profile imported."),
                }
                if existing_sp:
                    await self.db.safetyprofile.update(where={"id": existing_sp.id}, data=sp_fields)
                else:
                    await self.db.safetyprofile.create(
                        data={"ingredientId": ingredient_id, **sp_fields}
                    )

        return {
            "total_records": len(ingredients),
            "created_count": created_count,
            "updated_count": updated_count,
            "skipped_count": 0,
            "error_count": 0,
            "errors": [],
            "warnings": all_warnings,
            "matched_inci_terms": matched_inci_terms,
        }
