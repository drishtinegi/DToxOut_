"""
Knowledge builder for the AI Knowledge Engine.

Assembles a complete :class:`IngredientKnowledgeResponse` from an
already-loaded Prisma :class:`Ingredient` record.  This module
**never** performs database queries — it is a pure transformation
layer between the data-access layer (``IngredientService``) and the
API response layer.

Usage::

    from app.services.knowledge_builder import KnowledgeBuilder

    response = KnowledgeBuilder.build(ingredient_with_relations)
"""

from __future__ import annotations

from prisma.models import Ingredient as PrismaIngredient

from app.schemas.knowledge import (
    IngredientBasicInfo,
    IngredientBenefitResult,
    IngredientCategoryResult,
    IngredientKnowledgeResponse,
    RegulationResult,
    SafetyProfileResult,
    ScientificReferenceResult,
)


class KnowledgeBuilder:
    """Stateless builder that transforms a Prisma Ingredient into a response.

    Every method is a pure function — no I/O, no side effects, no
    database access.  The :meth:`build` entry point orchestrates the
    sub-builders and returns a fully populated
    :class:`IngredientKnowledgeResponse`.

    Example::

        response = KnowledgeBuilder.build(ingredient)
    """

    @staticmethod
    def build(ingredient: PrismaIngredient) -> IngredientKnowledgeResponse:
        """Assemble the full knowledge response from a loaded Ingredient.

        Expects the ingredient to have been fetched with the following
        Prisma ``include`` payload::

            {
                "category": True,
                "safetyProfile": True,
                "aliases": True,
                "benefits": True,
                "regulations": True,
                "scientificReferences": True,
            }

        Missing relations are handled gracefully: one-to-one fields
        map to ``None``, collections map to empty lists.

        Args:
            ingredient: A fully-loaded Prisma :class:`Ingredient` record
                with all nested relations eager-loaded.

        Returns:
            A populated :class:`IngredientKnowledgeResponse`.
        """
        return IngredientKnowledgeResponse(
            ingredient=KnowledgeBuilder._build_basic_info(ingredient),
            category=KnowledgeBuilder._build_category(ingredient),
            aliases=KnowledgeBuilder._build_aliases(ingredient),
            benefits=KnowledgeBuilder._build_benefits(ingredient),
            safety_profile=KnowledgeBuilder._build_safety_profile(ingredient),
            regulations=KnowledgeBuilder._build_regulations(ingredient),
            scientific_references=KnowledgeBuilder._build_scientific_references(
                ingredient,
            ),
        )

    # ------------------------------------------------------------------
    # Private sub-builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_basic_info(ingredient: PrismaIngredient) -> IngredientBasicInfo:
        """Extract core flat columns from the Ingredient record.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            An :class:`IngredientBasicInfo` with the ingredient's scalar fields.
        """
        return IngredientBasicInfo(
            id=ingredient.id,
            inci_name=ingredient.inciName,
            common_name=ingredient.commonName,
            description=ingredient.description,
            function=ingredient.function,
            safety_rating=ingredient.safetyRating,
            evidence_level=ingredient.evidenceLevel,
            created_at=ingredient.createdAt,
        )

    @staticmethod
    def _build_category(
        ingredient: PrismaIngredient,
    ) -> IngredientCategoryResult | None:
        """Transform the category relation into a response model.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            An :class:`IngredientCategoryResult` or ``None`` if the
            ingredient has no assigned category.
        """
        cat = ingredient.category
        if cat is None:
            return None
        return IngredientCategoryResult(
            id=cat.id,
            name=cat.name,
            description=cat.description,
        )

    @staticmethod
    def _build_aliases(ingredient: PrismaIngredient) -> list[str]:
        """Extract alias strings from the aliases relation.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            A list of alias strings (may be empty).
        """
        return [alias.alias for alias in (ingredient.aliases or [])]

    @staticmethod
    def _build_benefits(
        ingredient: PrismaIngredient,
    ) -> list[IngredientBenefitResult]:
        """Transform benefit records into response models.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            A list of :class:`IngredientBenefitResult` (may be empty).
        """
        return [
            IngredientBenefitResult(title=b.title, description=b.description)
            for b in (ingredient.benefits or [])
        ]

    @staticmethod
    def _build_safety_profile(
        ingredient: PrismaIngredient,
    ) -> SafetyProfileResult | None:
        """Transform the safety profile relation into a response model.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            A :class:`SafetyProfileResult` or ``None`` if no safety
            profile has been recorded.
        """
        sp = ingredient.safetyProfile
        if sp is None:
            return None
        return SafetyProfileResult(
            risk_level=sp.riskLevel,
            allergy_risk=sp.allergyRisk,
            pregnancy_risk=sp.pregnancyRisk,
            acne_risk=sp.acneRisk,
            sensitive_skin_risk=sp.sensitiveSkinRisk,
            explanation=sp.explanation,
        )

    @staticmethod
    def _build_regulations(
        ingredient: PrismaIngredient,
    ) -> list[RegulationResult]:
        """Transform regulation records into response models.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            A list of :class:`RegulationResult` (may be empty).
        """
        return [
            RegulationResult(
                country=r.country,
                regulatory_status=r.regulatoryStatus,
                restriction_details=r.restrictionDetails,
                source=r.source,
            )
            for r in (ingredient.regulations or [])
        ]

    @staticmethod
    def _build_scientific_references(
        ingredient: PrismaIngredient,
    ) -> list[ScientificReferenceResult]:
        """Transform scientific reference records into response models.

        Args:
            ingredient: The Prisma :class:`Ingredient` record.

        Returns:
            A list of :class:`ScientificReferenceResult` (may be empty).
        """
        return [
            ScientificReferenceResult(
                title=sr.title,
                organization=sr.organization,
                publication_year=sr.publicationYear,
                evidence_summary=sr.evidenceSummary,
                source_url=sr.sourceUrl,
            )
            for sr in (ingredient.scientificReferences or [])
        ]
