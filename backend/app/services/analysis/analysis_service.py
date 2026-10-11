"""
AI Ingredient Intelligence Engine — orchestrator service.

Coordinates the risk engine, explanation engine, recommendation
engine, and confidence engine to produce a comprehensive
:class:`AnalysisResult` for a scanned product.

This service is designed as a **plugin-ready** orchestrator: each
sub-engine can be replaced with an AI-powered implementation without
changing the public interface or the calling route.

Usage from a route handler::

    from app.services.analysis.analysis_service import AnalysisService
    from app.database import db

    service = AnalysisService(db)
    result = await service.analyze_product(
        product_name="Moisturizer",
        ingredients=["Water", "Niacinamide", "Panthenol"],
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from prisma import Prisma
from prisma.models import Ingredient as PrismaIngredient

from app.schemas.analysis import AnalysisResult
from app.services.analysis.confidence_engine import ConfidenceEngine
from app.services.analysis.explanation_engine import ExplanationEngine
from app.services.analysis.recommendation_engine import RecommendationEngine
from app.services.risk_engine import ProductRiskEngine


class AnalysisService:
    """Orchestrator that coordinates all analysis sub-engines.

    Receives a Prisma client for database lookups and delegates
    scoring, explanation generation, and recommendation to dedicated
    engines.  Each engine is instantiated once so that future
    implementations can be swapped via dependency injection or
    configuration.

    Example::

        service = AnalysisService(db)
        result = await service.analyze_product(
            product_name="Daily Moisturizer SPF 30",
            ingredients=["Water", "Niacinamide", "Panthenol"],
        )
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db
        self._risk_engine = ProductRiskEngine()
        self._explanation_engine = ExplanationEngine()
        self._recommendation_engine = RecommendationEngine()
        self._confidence_engine = ConfidenceEngine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_product(
        self,
        product_name: str,
        ingredients: list[str],
        image_url: Optional[str] = None,
    ) -> AnalysisResult:
        """Run a full deterministic analysis on the supplied ingredient list.

        Execution flow:

            1. Look up each ingredient in the knowledge base.
            2. Delegate to the risk engine for overall scoring.
            3. Delegate to the explanation engine for a product-level
               summary, reasons, and per-ingredient breakdowns.
            4. Delegate to the recommendation engine for skin-type
               suitability, precautions, and usage guidance.
            5. Delegate to the confidence engine to estimate analysis
               reliability based on ingredient data quality.
            6. Assemble and return the final :class:`AnalysisResult`.

        Args:
            product_name: Display name of the product being analysed.
            ingredients: Raw ingredient name strings submitted by the
                user (1–300 items).
            image_url: Optional URL of the product image, preserved
                for future use in the response.

        Returns:
            A fully populated :class:`AnalysisResult` containing the
            overall analysis, product explanation, recommendations,
            confidence score, and analysis timestamp.

        Raises:
            ValueError: If the ingredient list is empty.
        """
        if not ingredients:
            raise ValueError("Cannot analyze an empty ingredient list.")

        # Step 1 — Look up ingredients and their safety profiles.
        ingredient_data = await self._resolve_ingredients(ingredients)

        # Step 2 — Compute overall scores via the risk engine.
        safety_ratings = [
            data["safety_rating"] for data in ingredient_data
        ]
        overall = self._risk_engine.analyze(safety_ratings)

        # Step 3 — Build the product explanation via the explanation engine.
        product_explanation = (
            self._explanation_engine.build_product_explanation(
                overall_score=overall.overall_score,
                overall_risk=overall.overall_risk,
                ingredient_count=overall.ingredient_count,
                ingredient_data=ingredient_data,
            )
        )

        # Populate the overall summary from the explanation engine.
        overall.summary = product_explanation.summary

        # Step 4 — Generate the product recommendation via the recommendation engine.
        recommendations = self._recommendation_engine.generate_recommendations(
            ingredient_data=ingredient_data,
            overall=overall,
        )

        # Step 5 — Compute confidence score via the confidence engine.
        resolved_ingredients = [
            data["ingredient"] for data in ingredient_data
        ]
        confidence_score = self._confidence_engine.calculate_confidence(
            ingredients=resolved_ingredients,
        )

        # Step 6 — Assemble the final result.
        return AnalysisResult(
            product_name=product_name,
            ingredient_count=overall.ingredient_count,
            overall_analysis=overall,
            product_explanation=product_explanation,
            recommendations=recommendations,
            confidence_score=confidence_score,
            analysis_timestamp=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------
    # Private helpers — data resolution
    # ------------------------------------------------------------------

    async def _resolve_ingredients(
        self,
        ingredients: list[str],
    ) -> list[dict[str, Any]]:
        """Look up each ingredient and its safety profile in the database.

        Ingredients that cannot be found in the knowledge base are
        silently excluded from the result set.

        Args:
            ingredients: Raw ingredient name strings.

        Returns:
            A list of dicts, each containing:

            * ``ingredient`` — the Prisma :class:`Ingredient` record
            * ``safety_profile`` — the associated
              :class:`SafetyProfile` or ``None``
            * ``safety_rating`` — the numeric rating from the
              ingredient record
        """
        unique_names = list(dict.fromkeys(ingredients))

        batch_conditions: list[dict[str, Any]] = [
            {"inciName": {"contains": name, "mode": "insensitive"}}
            for name in unique_names
        ]

        matched = await self._db.ingredient.find_many(
            where={"OR": batch_conditions},
        )

        matched_ids: list[str] = []
        ingredient_by_id: dict[str, Any] = {}
        for ing in matched:
            matched_ids.append(ing.id)
            ingredient_by_id[ing.id] = ing

        safety_profiles: dict[str, Any] = {}
        if matched_ids:
            profiles = await self._db.safetyprofile.find_many(
                where={"ingredientId": {"in": matched_ids}},
            )
            for sp in profiles:
                safety_profiles[sp.ingredientId] = sp

        resolved: list[dict[str, Any]] = []
        for name in unique_names:
            found = None
            for ing in matched:
                ing_lower = ing.inciName.lower()
                if name.lower() in ing_lower or ing_lower in name.lower():
                    found = ing
                    break

            if found is None:
                continue

            resolved.append(
                {
                    "ingredient": found,
                    "safety_profile": safety_profiles.get(found.id),
                    "safety_rating": found.safetyRating,
                }
            )

        return resolved
