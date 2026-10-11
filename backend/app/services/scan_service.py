"""
Scan Analysis Engine and Scan History business logic service.

This module contains two responsibilities:

1. **Analysis Engine** — the ingredient analysis pipeline: normalization,
   database lookup, risk classification, scoring, and response assembly.

2. **Scan History** — persistence of user scans and their detected
   ingredients in PostgreSQL via Prisma.

Usage from a route handler::

    from app.services.scan_service import ScanService
    from app.database import db

    service = ScanService(db)

    # Analysis
    response = await service.analyze_ingredients(["Water", "Niacinamide"])

    # History
    scan = await service.create_scan(user_id, "Moisturizer", 8.5)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

from prisma import Prisma
from prisma.errors import PrismaError
from prisma.models import Scan as PrismaScan
from prisma.models import ScanIngredient as PrismaScanIngredient

from app.core.exceptions import DomainError
from app.schemas.scan import (
    MEDICAL_DISCLAIMER,
    IngredientAnalysis,
    RecommendationWarning,
    ScanResponse,
    UnknownIngredient,
)
from app.services.analysis.analysis_service import AnalysisService
from app.services.recommendation_service import RecommendationService
from app.services.risk_engine import ProductRiskEngine
from app.utils.ingredient_matcher import IngredientMatcher, normalize_ingredient_name


# ---------------------------------------------------------------------------
# Risk thresholds
# ---------------------------------------------------------------------------

_RISK_THRESHOLDS: list[tuple[float, str]] = [
    (9.0, "LOW"),
    (7.0, "MODERATE"),
    (5.0, "HIGH"),
]
_DEFAULT_RISK = "VERY_HIGH"

_UNKNOWN_REASON = "Ingredient not found in knowledge base."

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScanNotFoundError(DomainError):
    """Raised when a scan cannot be found by the given criteria."""

    status_code = 404

    def __init__(self, detail: str = "Scan not found") -> None:
        super().__init__(detail)


class ScanAccessDeniedError(DomainError):
    """Raised when a user attempts to access a scan they do not own."""

    status_code = 403

    def __init__(
        self,
        detail: str = "Access denied: you do not own this scan",
    ) -> None:
        super().__init__(detail)


class InvalidScanError(DomainError):
    """Raised when scan data is invalid or incomplete."""

    status_code = 400

    def __init__(self, detail: str = "Invalid scan data") -> None:
        super().__init__(detail)


class DuplicateScanIngredientError(DomainError):
    """Raised when attempting to add a duplicate ingredient to a scan."""

    status_code = 409

    def __init__(self, scan_id: str, ingredient_id: str) -> None:
        super().__init__(
            f"Ingredient '{ingredient_id}' already exists in scan '{scan_id}'"
        )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanIngredientInput:
    """Input data for a single ingredient to add to a scan.

    Attributes:
        ingredient_name: INCI name used to look up the canonical
            :class:`Ingredient` in the knowledge base.
        detected_name: Original ingredient name as detected by the
            analysis engine (may differ from the INCI name).
        confidence_score: Confidence of the detection, between 0.0
            and 1.0 inclusive.
    """

    ingredient_name: str
    detected_name: str
    confidence_score: float


# ---------------------------------------------------------------------------
# Prisma ``include`` payloads
# ---------------------------------------------------------------------------

_SCAN_FULL_INCLUDE: dict[str, Any] = {
    "user": True,
    "scanIngredients": {
        "include": {
            "ingredient": {
                "include": {
                    "safetyProfile": True,
                    "category": True,
                    "benefits": True,
                    "aliases": True,
                }
            }
        }
    },
}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ScanService:
    """Stateless service containing all scan-analysis and scan-history
    business logic.

    Instantiate with a connected Prisma client and call its async methods::

        service = ScanService(db)
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db
        self._recommendation_service = RecommendationService()
        self._analysis_service = AnalysisService(db)
        self._product_risk_engine = ProductRiskEngine()

    # ------------------------------------------------------------------
    # Analysis Engine
    # ------------------------------------------------------------------

    async def analyze_ingredients(
        self,
        ingredients: list[str],
        selected_jurisdiction: Optional[str] = None,
    ) -> ScanResponse:
        """Perform a full analysis of the supplied ingredient names.

        Steps:
            1. Normalize every incoming name and deduplicate preserving order.
            2. Look up candidates in DB with eager-loaded relations.
            3. Use IngredientMatcher for strict hierarchical matching.
            4. Compute composite risk and confidence via ProductRiskEngine.
            5. Generate recommendations and warnings with safe unknown policies.
            6. Return a fully populated ``ScanResponse``.

        Args:
            ingredients: Raw ingredient name strings (1-300 items).
            selected_jurisdiction: Optional country/jurisdiction code (e.g. 'EU', 'US').

        Returns:
            A ``ScanResponse`` containing scores, risk classifications,
            categorized ingredient details, and recommendation data.

        Raises:
            ValueError: If the ingredient list is empty.
        """
        if not ingredients:
            raise ValueError("Ingredient list must not be empty.")

        # Step 1 – Deduplicate while preserving first-seen order
        seen_norm: set[str] = set()
        deduped_inputs: list[tuple[str, str]] = []
        for raw in ingredients:
            norm = normalize_ingredient_name(raw)
            if norm and norm not in seen_norm:
                seen_norm.add(norm)
                deduped_inputs.append((raw, norm))

        if not deduped_inputs:
            raise ValueError("Ingredient list must not be empty.")

        unique_normalized_names = [norm for _, norm in deduped_inputs]

        # Step 2 – Batch DB lookup with eager loaded relations
        candidate_ingredients = await self._db.ingredient.find_many(
            where={
                "OR": [
                    {"inciName": {"in": unique_normalized_names, "mode": "insensitive"}},
                    {"commonName": {"in": unique_normalized_names, "mode": "insensitive"}},
                    {
                        "aliases": {
                            "some": {
                                "alias": {"in": unique_normalized_names, "mode": "insensitive"}
                            }
                        }
                    },
                ]
            },
            include={
                "safetyProfile": True,
                "aliases": True,
                "regulations": True,
                "scientificReferences": True,
            },
        )

        # Fallback to loading all ingredients if fuzzy matching candidates might be needed
        if len(candidate_ingredients) < len(unique_normalized_names):
            all_db_ingredients = await self._db.ingredient.find_many(
                include={
                    "safetyProfile": True,
                    "aliases": True,
                    "regulations": True,
                    "scientificReferences": True,
                },
            )
            candidate_ingredients = all_db_ingredients

        # Step 3 – Match deduplicated ingredients
        recognized: list[IngredientAnalysis] = []
        unknown: list[UnknownIngredient] = []
        resolved_for_risk_engine: list[dict[str, Any]] = []
        unknown_names_for_risk_engine: list[str] = []
        ingredient_profiles: list[dict[str, Optional[str]]] = []
        regulatory_warnings: list[RecommendationWarning] = []
        has_banned_in_jurisdiction = False

        target_jurisdiction = selected_jurisdiction.strip().upper() if selected_jurisdiction else None

        for raw_name, norm_name in deduped_inputs:
            match_result = IngredientMatcher.match_single(
                norm_name, candidate_ingredients
            )

            if match_result.ingredient is not None:
                ing = match_result.ingredient
                sp = getattr(ing, "safetyProfile", None)
                sp_risk = getattr(sp, "riskLevel", None) if sp is not None else None

                # Regulations (jurisdiction-specific from DB)
                raw_regs = getattr(ing, "regulations", []) or []
                regs_list = []
                for reg in raw_regs:
                    reg_status = (
                        getattr(reg, "regulatoryStatus", None)
                        or getattr(reg, "regulatory_status", None)
                    )
                    reg_country = getattr(reg, "country", "")
                    reg_jur = getattr(reg, "jurisdiction", None) or reg_country

                    retrieved_date_str = (
                        reg.retrievedDate.isoformat()
                        if getattr(reg, "retrievedDate", None)
                        else None
                    )
                    effective_date_str = (
                        reg.effectiveDate.isoformat()
                        if getattr(reg, "effectiveDate", None)
                        else None
                    )

                    r_dict = {
                        "country": reg_country,
                        "jurisdiction": reg_jur,
                        "status": reg_status,
                        "regulatory_status": reg_status,
                        "restriction_details": getattr(reg, "restrictionDetails", ""),
                        "source": getattr(reg, "source", ""),
                        "source_organization": getattr(reg, "sourceOrganization", None),
                        "source_url": getattr(reg, "sourceUrl", None),
                        "retrieved_date": retrieved_date_str,
                        "effective_date": effective_date_str,
                        "verification_status": getattr(reg, "verificationStatus", "UNVERIFIED"),
                        "product_category": getattr(reg, "productCategory", None),
                        "concentration_limit": getattr(reg, "concentrationLimit", None),
                    }
                    regs_list.append(r_dict)

                    # Evaluate regulatory warning rules for selected jurisdiction
                    if target_jurisdiction:
                        is_match = (
                            reg_jur.strip().upper() == target_jurisdiction
                            or reg_country.strip().upper() == target_jurisdiction
                        )
                        if is_match:
                            if reg_status == "BANNED":
                                has_banned_in_jurisdiction = True
                                regulatory_warnings.append(
                                    RecommendationWarning(
                                        type="REGULATORY",
                                        severity="HIGH",
                                        title=f"Regulatory Warning: Banned in {target_jurisdiction}",
                                        message=f"'{ing.inciName}' is BANNED in {target_jurisdiction}. {reg.restrictionDetails}",
                                        ingredient_name=ing.inciName,
                                    )
                                )
                            elif reg_status == "RESTRICTED":
                                regulatory_warnings.append(
                                    RecommendationWarning(
                                        type="REGULATORY",
                                        severity="MODERATE",
                                        title=f"Regulatory Restriction in {target_jurisdiction}",
                                        message=f"'{ing.inciName}' is RESTRICTED in {target_jurisdiction}. {reg.restrictionDetails}",
                                        ingredient_name=ing.inciName,
                                    )
                                )
                            elif reg_status == "PENDING_REVIEW":
                                regulatory_warnings.append(
                                    RecommendationWarning(
                                        type="REGULATORY",
                                        severity="LOW",
                                        title=f"Verification Incomplete ({target_jurisdiction})",
                                        message=f"'{ing.inciName}' regulatory status verification is incomplete in {target_jurisdiction}.",
                                        ingredient_name=ing.inciName,
                                    )
                                )

                # Scientific References from DB
                refs_list = (
                    [
                        {
                            "title": ref.title,
                            "organization": ref.organization,
                            "publication_year": ref.publicationYear,
                            "evidence_summary": ref.evidenceSummary,
                            "source_url": ref.sourceUrl,
                        }
                        for ref in (getattr(ing, "scientificReferences", []) or [])
                    ]
                    if getattr(ing, "scientificReferences", None)
                    else None
                )

                composite_ing_risk = ProductRiskEngine.score_ingredient(
                    safety_rating=ing.safetyRating,
                    risk_level=sp_risk,
                    evidence_level=getattr(ing, "evidenceLevel", None),
                )
                ing_risk_level = ProductRiskEngine.calculate_risk_level(
                    composite_ing_risk
                )

                match_type_val = (
                    match_result.match_type.value
                    if hasattr(match_result.match_type, "value")
                    else str(match_result.match_type)
                )

                recognized.append(
                    IngredientAnalysis(
                        inci_name=ing.inciName,
                        common_name=ing.commonName,
                        description=ing.description,
                        function=ing.function,
                        safety_rating=ing.safetyRating,
                        evidence_level=str(ing.evidenceLevel),
                        risk=ing_risk_level,
                        original_detected_input=raw_name,
                        match_type=match_type_val,
                        match_confidence=match_result.match_confidence,
                        manual_confirmation_recommended=match_result.manual_confirmation_recommended,
                        regulations=regs_list if regs_list else None,
                        scientific_references=refs_list if refs_list else None,
                    )
                )

                resolved_for_risk_engine.append(
                    {
                        "inci_name": ing.inciName,
                        "common_name": ing.commonName,
                        "safety_rating": ing.safetyRating,
                        "risk_level": sp_risk,
                        "evidence_level": getattr(ing, "evidenceLevel", None),
                    }
                )

                ingredient_profiles.append(
                    {
                        "inci_name": ing.inciName,
                        "risk_level": sp_risk,
                        "pregnancy_risk": getattr(sp, "pregnancyRisk", None)
                        if sp is not None
                        else None,
                        "acne_risk": getattr(sp, "acneRisk", None)
                        if sp is not None
                        else None,
                        "sensitive_skin_risk": getattr(
                            sp, "sensitiveSkinRisk", None
                        )
                        if sp is not None
                        else None,
                        "allergy_risk": getattr(sp, "allergyRisk", None)
                        if sp is not None
                        else None,
                    }
                )
            else:
                unknown.append(
                    UnknownIngredient(
                        name=raw_name,
                        reason=_UNKNOWN_REASON,
                        match_type="UNKNOWN",
                    )
                )
                unknown_names_for_risk_engine.append(raw_name)

        # Step 4 – Scoring & Risk Calculation via ProductRiskEngine
        recognized_count = len(recognized)
        unknown_count = len(unknown)
        total_unique = recognized_count + unknown_count
        recognition_coverage = (
            round((recognized_count / total_unique * 100.0), 2)
            if total_unique > 0
            else 0.0
        )

        if recognized_count == 0:
            # Policy when ALL ingredients are unknown
            overall_score = 0.0
            overall_risk = "VERY_HIGH"
            confidence_score = 0
            summary = (
                "None of the provided ingredients could be identified in the "
                "DToxOut knowledge base."
            )
            recommendation_label = "USE WITH CAUTION"
            recommendation_msg = (
                "None of the submitted ingredients could be identified in the "
                "DToxOut knowledge base. Cautious evaluation is recommended."
            )
            warnings_list = [
                RecommendationWarning(
                    type="INCOMPLETE_COVERAGE",
                    severity="HIGH",
                    title="All Ingredients Unknown",
                    message=(
                        "None of the ingredients could be matched in the "
                        "database. Product safety cannot be evaluated."
                    ),
                    ingredient_name="N/A",
                )
            ]
        else:
            product_risk_res = self._product_risk_engine.analyze(
                resolved_ingredients=resolved_for_risk_engine,
                unknown_names=unknown_names_for_risk_engine,
            )
            overall_score = product_risk_res.overall_score
            overall_risk = product_risk_res.overall_risk_level
            confidence_score = product_risk_res.confidence
            summary = self._generate_summary(recognized_count, unknown_count)

            # Recommendation engine
            rec_res = self._recommendation_service.generate_recommendation(
                overall_risk_level=overall_risk,
                ingredient_profiles=ingredient_profiles,
            )
            recommendation_label = rec_res.recommendation
            recommendation_msg = rec_res.recommendation_message
            warnings_list = list(rec_res.warnings)

            # Add regulatory warnings for selected jurisdiction
            if regulatory_warnings:
                warnings_list.extend(regulatory_warnings)

            # Update recommendation label if BANNED in selected jurisdiction
            if has_banned_in_jurisdiction:
                recommendation_label = "AVOID"

            # Cautious unknown handling rule: no unqualified SAFE when unknown ingredients exist
            if unknown_count > 0 and recommendation_label == "SAFE":
                recommendation_label = "USE WITH CAUTION"
                warnings_list.append(
                    RecommendationWarning(
                        type="INCOMPLETE_COVERAGE",
                        severity="MODERATE",
                        title="Incomplete Ingredient Coverage",
                        message=(
                            f"{unknown_count} ingredient(s) could not be identified "
                            f"in the database. Product safety assessment is incomplete."
                        ),
                        ingredient_name="N/A",
                    )
                )

        # Step 5 – Extended Analysis Engine
        analysis_result = None
        try:
            product_name = self._generate_product_name(ingredients)
            analysis_result = await self._analysis_service.analyze_product(
                product_name=product_name,
                ingredients=ingredients,
            )
        except Exception:
            logger.warning(
                "Extended analysis failed; returning base scan response only",
                exc_info=True,
            )

        # Step 6 – Assemble response
        response = ScanResponse(
            overall_score=overall_score,
            overall_risk=overall_risk,
            recognized_count=recognized_count,
            unknown_count=unknown_count,
            recognized_ingredients=recognized,
            unknown_ingredients=unknown,
            analysis_summary=summary,
            recommendation=recommendation_label,
            recommendation_message=recommendation_msg,
            warnings=warnings_list,
            confidence_score=confidence_score,
            recognition_coverage=recognition_coverage,
            disclaimer=MEDICAL_DISCLAIMER,
        )

        # Merge extended analysis fields when available
        if analysis_result is not None:
            if analysis_result.confidence_score is not None:
                response.confidence_score = analysis_result.confidence_score
            response.analysis_timestamp = analysis_result.analysis_timestamp
            response.explanation_summary = (
                analysis_result.product_explanation.summary
            )
            response.explanation_reasons = (
                analysis_result.product_explanation.reasons
            )
            response.recommended_for = (
                analysis_result.recommendations.recommended_for
            )
            response.precautions = analysis_result.recommendations.precautions
            response.usage_guidance = (
                analysis_result.recommendations.usage_guidance
            )
            response.ingredient_explanations = [
                ie.model_dump()
                for ie in analysis_result.product_explanation.ingredient_explanations
            ]

        return response

    # ------------------------------------------------------------------
    # Scan History — Create
    # ------------------------------------------------------------------

    async def create_scan(
        self,
        user_id: str,
        product_name: str,
        overall_risk_score: float,
        image_url: Optional[str] = None,
    ) -> PrismaScan:
        """Create a new scan record for the authenticated user.

        Validates that the user exists, the product name is non-empty,
        and the risk score is within the valid 0–10 range.

        Args:
            user_id: UUID of the authenticated user who owns this scan.
            product_name: Display name of the scanned product.
            overall_risk_score: Aggregate risk score (0.0 – 10.0).
            image_url: Optional URL of the product image.

        Returns:
            The newly created :class:`Scan` record.

        Raises:
            InvalidScanError: If the user does not exist, the product
                name is empty, or the risk score is out of range.

        Example::

            scan = await service.create_scan(
                user_id="some-uuid",
                product_name="Daily Moisturizer SPF 30",
                overall_risk_score=8.5,
                image_url="https://example.com/image.jpg",
            )
        """
        user = await self._db.user.find_unique(where={"id": user_id})
        if user is None:
            raise InvalidScanError(
                f"User with id '{user_id}' not found"
            )

        stripped_name = product_name.strip()
        if not stripped_name:
            raise InvalidScanError("Product name must not be empty")

        if not (0.0 <= overall_risk_score <= 10.0):
            raise InvalidScanError(
                "Overall risk score must be between 0.0 and 10.0"
            )

        data: dict[str, Any] = {
            "userId": user_id,
            "productName": stripped_name,
            "overallRiskScore": overall_risk_score,
        }
        if image_url is not None:
            data["imageUrl"] = image_url

        scan = await self._db.scan.create(data=data)
        return scan

    async def persist_analysis(
        self,
        user_id: str,
        ingredients: list[str],
        overall_score: float,
    ) -> None:
        """Persist a completed analysis to the scan history.

        Creates a :class:`Scan` record and all associated
        :class:`ScanIngredient` records inside a single database
        transaction.  If any step fails the entire transaction is
        rolled back and the error is logged — this method **never**
        raises.

        This is intended to be called *after* a successful analysis
        so that the primary operation (returning the analysis to the
        client) is never affected by persistence failures.

        Args:
            user_id: UUID of the authenticated user.
            ingredients: Original raw ingredient name list that was
                submitted for analysis.
            overall_score: The aggregate safety score computed by the
                analysis engine.

        Example::

            await service.persist_analysis(
                user_id="some-uuid",
                ingredients=["Water", "Niacinamide", "Panthenol"],
                overall_score=8.5,
            )
        """
        try:
            product_name = self._generate_product_name(ingredients)

            async with self._db.tx() as tx:
                scan = await tx.scan.create(
                    data={
                        "userId": user_id,
                        "productName": product_name,
                        "overallRiskScore": overall_score,
                    }
                )

                unique_ingredients = list(dict.fromkeys(ingredients))

                batch_conditions = [
                    {"inciName": {"contains": name, "mode": "insensitive"}}
                    for name in unique_ingredients
                ]

                matched = await tx.ingredient.find_many(
                    where={"OR": batch_conditions},
                )

                lookup: dict[str, str] = {}
                for ing in matched:
                    ing_lower = ing.inciName.lower()
                    for name in unique_ingredients:
                        if name.lower() in ing_lower or ing_lower in name.lower():
                            if name not in lookup:
                                lookup[name] = ing.id
                            break

                for name in ingredients:
                    ingredient_id = lookup.get(name)
                    if ingredient_id is None:
                        continue

                    await tx.scaningredient.create(
                        data={
                            "scanId": scan.id,
                            "ingredientId": ingredient_id,
                            "detectedName": name,
                            "confidenceScore": 1.0,
                        }
                    )

        except PrismaError as exc:
            logger.error(
                "Failed to persist scan for user %s: "
                "operation=persist_analysis ingredient_count=%d error=%s",
                user_id,
                len(ingredients),
                type(exc).__name__,
            )
        except Exception as exc:
            logger.error(
                "Unexpected error persisting scan for user %s: "
                "operation=persist_analysis error_type=%s",
                user_id,
                type(exc).__name__,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Scan History — Add Ingredients
    # ------------------------------------------------------------------

    async def add_scan_ingredients(
        self,
        scan_id: str,
        ingredients: list[ScanIngredientInput],
    ) -> list[PrismaScanIngredient]:
        """Add detected ingredients to an existing scan.

        For each ingredient the canonical :class:`Ingredient` record is
        looked up by INCI name (case-insensitive).  If found, a
        :class:`ScanIngredient` junction record is created.

        Ingredients whose INCI name cannot be found in the knowledge
        base are silently skipped.

        Args:
            scan_id: UUID of the scan to attach ingredients to.
            ingredients: List of :class:`ScanIngredientInput` data objects
                describing each detected ingredient.

        Returns:
            List of newly created :class:`ScanIngredient` records.  May
            be shorter than the input list when missing ingredients
            were skipped.

        Raises:
            ScanNotFoundError: If no scan with the given ID exists.
            InvalidScanError: If the ingredients list is empty.
            DuplicateScanIngredientError: If an ingredient is already
                linked to this scan.

        Example::

            inputs = [
                ScanIngredientInput(
                    ingredient_name="Niacinamide",
                    detected_name="Niacinamide",
                    confidence_score=0.95,
                ),
            ]
            created = await service.add_scan_ingredients(scan.id, inputs)
        """
        scan = await self._db.scan.find_unique(where={"id": scan_id})
        if scan is None:
            raise ScanNotFoundError(
                f"Scan with id '{scan_id}' not found"
            )

        if not ingredients:
            raise InvalidScanError("Ingredients list must not be empty")

        created: list[PrismaScanIngredient] = []

        for ingredient_input in ingredients:
            scan_ingredient = await self._create_single_scan_ingredient(
                scan_id=scan_id,
                ingredient_input=ingredient_input,
            )
            if scan_ingredient is not None:
                created.append(scan_ingredient)

        return created

    # ------------------------------------------------------------------
    # Scan History — Read
    # ------------------------------------------------------------------

    async def get_scan_by_id(
        self,
        scan_id: str,
        user_id: str,
    ) -> PrismaScan:
        """Return a fully populated scan by its ID.

        Only the scan owner may access the scan.  The returned object
        includes the owning user, all scan ingredients, and each
        ingredient's safety profile, category, benefits, and aliases.

        Args:
            scan_id: UUID of the scan to retrieve.
            user_id: UUID of the authenticated user (ownership check).

        Returns:
            The :class:`Scan` record with all nested relations populated.

        Raises:
            ScanNotFoundError: If no scan with this ID exists.
            ScanAccessDeniedError: If the requesting user does not own
                this scan.

        Example::

            scan = await service.get_scan_by_id(scan_id, user_id)
            # scan.scanIngredients[0].ingredient.safetyProfile
        """
        scan = await self._db.scan.find_unique(
            where={"id": scan_id},
            include=_SCAN_FULL_INCLUDE,
        )
        if scan is None:
            raise ScanNotFoundError(
                f"Scan with id '{scan_id}' not found"
            )

        if scan.userId != user_id:
            raise ScanAccessDeniedError()

        return scan

    async def list_user_scans(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PrismaScan]:
        """Return scans belonging only to the authenticated user.

        Results are ordered by ``createdAt`` descending (newest first)
        and include full relation data for each scan.

        Args:
            user_id: UUID of the authenticated user.
            skip: Number of records to skip (for pagination).
                Defaults to ``0``.
            limit: Maximum number of records to return.
                Defaults to ``20``.

        Returns:
            A list of :class:`Scan` records (may be empty).

        Example::

            first_page = await service.list_user_scans(user_id, limit=10)
            next_page = await service.list_user_scans(
                user_id, skip=10, limit=10,
            )
        """
        scans = await self._db.scan.find_many(
            where={"userId": user_id},
            skip=skip,
            take=limit,
            order={"createdAt": "desc"},
            include=_SCAN_FULL_INCLUDE,
        )
        return scans

    # ------------------------------------------------------------------
    # Scan History — Delete
    # ------------------------------------------------------------------

    async def delete_scan(
        self,
        scan_id: str,
        user_id: str,
    ) -> dict[str, str]:
        """Delete a scan and all its associated ScanIngredient records.

        Only the scan owner may delete the scan.  ``ScanIngredient``
        rows are removed by the database cascade rule.

        Args:
            scan_id: UUID of the scan to delete.
            user_id: UUID of the authenticated user (ownership check).

        Returns:
            A confirmation dict with the deleted scan's ID and a
            success message.

        Raises:
            ScanNotFoundError: If no scan with this ID exists.
            ScanAccessDeniedError: If the requesting user does not own
                this scan.

        Example::

            result = await service.delete_scan(scan_id, user_id)
            # {"id": "...", "message": "Scan deleted successfully"}
        """
        scan = await self._db.scan.find_unique(where={"id": scan_id})
        if scan is None:
            raise ScanNotFoundError(
                f"Scan with id '{scan_id}' not found"
            )

        if scan.userId != user_id:
            raise ScanAccessDeniedError()

        await self._db.scan.delete(where={"id": scan_id})
        return {
            "id": scan_id,
            "message": "Scan deleted successfully",
        }

    # ------------------------------------------------------------------
    # Private helpers — Analysis Engine
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_risk(safety_rating: float) -> str:
        """Classify an individual ingredient's safety rating as a risk level.

        Args:
            safety_rating: Numeric safety score (0.0 – 10.0).

        Returns:
            One of LOW, MODERATE, HIGH, or VERY_HIGH.
        """
        for threshold, label in _RISK_THRESHOLDS:
            if safety_rating >= threshold:
                return label
        return _DEFAULT_RISK

    @staticmethod
    def _calculate_overall_risk(score: float) -> str:
        """Classify the aggregate product score as an overall risk level.

        Args:
            score: Aggregate safety score (0.0 – 10.0).

        Returns:
            One of LOW, MODERATE, HIGH, or VERY_HIGH.
        """
        for threshold, label in _RISK_THRESHOLDS:
            if score >= threshold:
                return label
        return _DEFAULT_RISK

    @staticmethod
    def _generate_summary(recognized_count: int, unknown_count: int) -> str:
        """Build a human-readable analysis summary sentence.

        Args:
            recognized_count: Number of ingredients matched in the database.
            unknown_count:    Number of ingredients not found.

        Returns:
            A single-sentence summary describing recognition results.
        """
        if recognized_count == 0:
            return (
                "No ingredients from the provided list exist in the "
                "DToxOut knowledge base."
            )

        if unknown_count == 0:
            return "All ingredients were successfully recognized."

        recognized_word = "ingredient" if recognized_count == 1 else "ingredients"
        unknown_word = "ingredient" if unknown_count == 1 else "ingredients"

        return (
            f"{recognized_count} {recognized_word} "
            f"{'was' if recognized_count == 1 else 'were'} recognized and "
            f"{unknown_count} {unknown_word} could not be identified."
        )

    # ------------------------------------------------------------------
    # Private helpers — Scan History
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_product_name(ingredients: list[str]) -> str:
        """Build a display name from a raw ingredient list.

        Produces a comma-separated string of the first few ingredients.
        If the list exceeds three items a ``" + N more"`` suffix is
        appended.  The result is always trimmed to 255 characters.

        Args:
            ingredients: Raw ingredient name strings.

        Returns:
            A non-empty product name suitable for display.

        Example::

            ScanService._generate_product_name(["Water", "Niacinamide"])
            # "Water, Niacinamide"

            ScanService._generate_product_name(
                ["Water", "Niacinamide", "Panthenol", "Glycerin", "Tocopherol"]
            )
            # "Water, Niacinamide, Panthenol + 2 more"
        """
        if not ingredients:
            return "Ingredient Analysis"

        max_preview = 3
        preview = ingredients[:max_preview]
        name = ", ".join(preview)

        remaining = len(ingredients) - max_preview
        if remaining > 0:
            name += f" + {remaining} more"

        return name[:255]

    async def _create_single_scan_ingredient(
        self,
        scan_id: str,
        ingredient_input: ScanIngredientInput,
    ) -> PrismaScanIngredient | None:
        """Create one ScanIngredient record, returning None if not found.

        Looks up the canonical :class:`Ingredient` by INCI name, checks
        for an existing junction record, and creates the
        :class:`ScanIngredient` if both checks pass.

        Args:
            scan_id: UUID of the parent scan.
            ingredient_input: Data object describing the detected
                ingredient.

        Returns:
            The newly created :class:`ScanIngredient`, or ``None`` if
            the ingredient was not found in the knowledge base.

        Raises:
            DuplicateScanIngredientError: If an ingredient with the same
                ID is already linked to this scan.
        """
        ingredient = await self._db.ingredient.find_first(
            where={
                "inciName": {
                    "equals": ingredient_input.ingredient_name,
                    "mode": "insensitive",
                }
            }
        )
        if ingredient is None:
            return None

        existing = await self._db.scaningredient.find_unique(
            where={
                "scanId_ingredientId": {
                    "scanId": scan_id,
                    "ingredientId": ingredient.id,
                }
            }
        )
        if existing is not None:
            raise DuplicateScanIngredientError(scan_id, ingredient.id)

        scan_ingredient = await self._db.scaningredient.create(
            data={
                "scanId": scan_id,
                "ingredientId": ingredient.id,
                "detectedName": ingredient_input.detected_name,
                "confidenceScore": ingredient_input.confidence_score,
            }
        )
        return scan_ingredient
