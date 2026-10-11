"""
Safety Profile business logic service.

All database operations for the SafetyProfile model live here.
API routes should call this service instead of querying Prisma directly.

Usage from a route handler::

    from app.services.safety_profile_service import SafetyProfileService
    from app.database import db

    service = SafetyProfileService(db)
    profile = await service.get_safety_profile_by_ingredient("some-uuid")
"""

from __future__ import annotations

from typing import Optional

from prisma import Prisma
from prisma.errors import PrismaError
from prisma.models import SafetyProfile

from app.core.exceptions import DomainError
from app.services.ingredient_service import IngredientNotFoundError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SafetyProfileNotFoundError(DomainError):
    """Raised when a safety profile cannot be found for the given ingredient."""

    status_code = 404

    def __init__(self, ingredient_id: str) -> None:
        super().__init__(
            f"Safety profile not found for ingredient '{ingredient_id}'"
        )


class SafetyProfileAlreadyExistsError(DomainError):
    """Raised when attempting to create a duplicate safety profile."""

    status_code = 409

    def __init__(self, ingredient_id: str) -> None:
        super().__init__(
            f"Safety profile already exists for ingredient '{ingredient_id}'"
        )


class SafetyProfileServiceError(DomainError):
    """Raised when an unexpected database or infrastructure error occurs.

    This exception wraps :class:`prisma.errors.PrismaError` so that
    raw Prisma internals are never exposed to API consumers.
    """

    status_code = 500

    def __init__(self, detail: str = "An unexpected error occurred") -> None:
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class SafetyProfileService:
    """Stateless service wrapping all SafetyProfile CRUD operations.

    Each :class:`Ingredient` may have at most **one** associated
    :class:`SafetyProfile`.  This service enforces that constraint
    and delegates ingredient-existence checks to the database directly
    (rather than instantiating an :class:`IngredientService`).

    Instantiate once per request (or once at startup if the ``db``
    client is shared) and call its async methods.

    Example::

        service = SafetyProfileService(db)
        profile = await service.get_safety_profile_by_ingredient("some-uuid")
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_safety_profile(
        self,
        ingredient_id: str,
        risk_level: str,
        allergy_risk: str,
        pregnancy_risk: str,
        acne_risk: str,
        sensitive_skin_risk: str,
        explanation: str,
    ) -> SafetyProfile:
        """Create a safety profile for an ingredient.

        Validates that:

        1. The ingredient exists in the knowledge base.
        2. No safety profile already exists for this ingredient.

        Args:
            ingredient_id: UUID of the ingredient to attach the profile to.
            risk_level: Overall risk classification.  Must be one of
                ``"LOW"``, ``"MODERATE"``, ``"HIGH"``, ``"VERY_HIGH"``.
            allergy_risk: Free-text allergy risk assessment.
            pregnancy_risk: Free-text pregnancy safety assessment.
            acne_risk: Free-text acne / comedogenicity assessment.
            sensitive_skin_risk: Free-text sensitive-skin suitability.
            explanation: Detailed safety explanation.

        Returns:
            The newly created :class:`SafetyProfile` record.

        Raises:
            IngredientNotFoundError: If no ingredient with the given
                ID exists in the knowledge base.
            SafetyProfileAlreadyExistsError: If a safety profile already
                exists for this ingredient.
            SafetyProfileServiceError: If an unexpected database error
                occurs.
        """
        try:
            # 1. Verify the ingredient exists.
            ingredient = await self._db.ingredient.find_unique(
                where={"id": ingredient_id}
            )
            if ingredient is None:
                raise IngredientNotFoundError(
                    f"Ingredient with id '{ingredient_id}' not found"
                )

            # 2. Prevent duplicate safety profiles.
            existing = await self._db.safetyprofile.find_unique(
                where={"ingredientId": ingredient_id}
            )
            if existing is not None:
                raise SafetyProfileAlreadyExistsError(ingredient_id)

            profile = await self._db.safetyprofile.create(
                data={
                    "ingredientId": ingredient_id,
                    "riskLevel": risk_level,
                    "allergyRisk": allergy_risk,
                    "pregnancyRisk": pregnancy_risk,
                    "acneRisk": acne_risk,
                    "sensitiveSkinRisk": sensitive_skin_risk,
                    "explanation": explanation,
                }
            )
            return profile

        except (
            IngredientNotFoundError,
            SafetyProfileAlreadyExistsError,
        ):
            raise
        except PrismaError as exc:
            raise SafetyProfileServiceError(
                f"Database error while creating safety profile: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_safety_profile_by_ingredient(
        self,
        ingredient_id: str,
    ) -> SafetyProfile:
        """Retrieve the safety profile for a specific ingredient.

        Args:
            ingredient_id: UUID of the ingredient whose safety profile
                to retrieve.

        Returns:
            The :class:`SafetyProfile` record for the given ingredient.

        Raises:
            SafetyProfileNotFoundError: If no safety profile exists for
                the given ingredient.
            SafetyProfileServiceError: If an unexpected database error
                occurs.
        """
        try:
            profile = await self._db.safetyprofile.find_unique(
                where={"ingredientId": ingredient_id}
            )
            if profile is None:
                raise SafetyProfileNotFoundError(ingredient_id)
            return profile

        except SafetyProfileNotFoundError:
            raise
        except PrismaError as exc:
            raise SafetyProfileServiceError(
                f"Database error while fetching safety profile: {exc}"
            ) from exc

    async def get_all_profiles(self) -> list[SafetyProfile]:
        """Retrieve all safety profiles from the knowledge base.

        Returns:
            A list of :class:`SafetyProfile` records (may be empty).

        Raises:
            SafetyProfileServiceError: If an unexpected database error
                occurs.
        """
        try:
            profiles = await self._db.safetyprofile.find_many()
            return profiles

        except PrismaError as exc:
            raise SafetyProfileServiceError(
                f"Database error while fetching safety profiles: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_safety_profile(
        self,
        ingredient_id: str,
        risk_level: Optional[str] = None,
        allergy_risk: Optional[str] = None,
        pregnancy_risk: Optional[str] = None,
        acne_risk: Optional[str] = None,
        sensitive_skin_risk: Optional[str] = None,
        explanation: Optional[str] = None,
    ) -> SafetyProfile:
        """Update an existing safety profile.

        Only the fields that are explicitly provided (non-``None``) are
        updated.  All parameters default to ``None`` so that omitting
        a field leaves it unchanged.

        Args:
            ingredient_id: UUID of the ingredient whose safety profile
                to update.
            risk_level: New risk classification (or ``None`` to keep).
            allergy_risk: New allergy risk text (or ``None`` to keep).
            pregnancy_risk: New pregnancy risk text (or ``None`` to keep).
            acne_risk: New acne risk text (or ``None`` to keep).
            sensitive_skin_risk: New sensitive-skin text (or ``None``
                to keep).
            explanation: New explanation text (or ``None`` to keep).

        Returns:
            The updated :class:`SafetyProfile` record.

        Raises:
            SafetyProfileNotFoundError: If no safety profile exists for
                the given ingredient.
            SafetyProfileServiceError: If an unexpected database error
                occurs.
        """
        try:
            # Verify the profile exists before attempting update.
            existing = await self._db.safetyprofile.find_unique(
                where={"ingredientId": ingredient_id}
            )
            if existing is None:
                raise SafetyProfileNotFoundError(ingredient_id)

            # Build the update payload from non-None fields only.
            update_data: dict[str, str] = {}
            if risk_level is not None:
                update_data["riskLevel"] = risk_level
            if allergy_risk is not None:
                update_data["allergyRisk"] = allergy_risk
            if pregnancy_risk is not None:
                update_data["pregnancyRisk"] = pregnancy_risk
            if acne_risk is not None:
                update_data["acneRisk"] = acne_risk
            if sensitive_skin_risk is not None:
                update_data["sensitiveSkinRisk"] = sensitive_skin_risk
            if explanation is not None:
                update_data["explanation"] = explanation

            if not update_data:
                # Nothing to update — return the existing record as-is.
                return existing

            profile = await self._db.safetyprofile.update(
                where={"ingredientId": ingredient_id},
                data=update_data,
            )
            return profile

        except SafetyProfileNotFoundError:
            raise
        except PrismaError as exc:
            raise SafetyProfileServiceError(
                f"Database error while updating safety profile: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_safety_profile(
        self,
        ingredient_id: str,
    ) -> dict[str, str]:
        """Delete a safety profile by its associated ingredient ID.

        Args:
            ingredient_id: UUID of the ingredient whose safety profile
                to delete.

        Returns:
            A confirmation dict containing the ingredient ID and a
            success message.

        Raises:
            SafetyProfileNotFoundError: If no safety profile exists for
                the given ingredient.
            SafetyProfileServiceError: If an unexpected database error
                occurs.
        """
        try:
            existing = await self._db.safetyprofile.find_unique(
                where={"ingredientId": ingredient_id}
            )
            if existing is None:
                raise SafetyProfileNotFoundError(ingredient_id)

            await self._db.safetyprofile.delete(
                where={"ingredientId": ingredient_id}
            )
            return {
                "ingredient_id": ingredient_id,
                "message": "Safety profile deleted successfully",
            }

        except SafetyProfileNotFoundError:
            raise
        except PrismaError as exc:
            raise SafetyProfileServiceError(
                f"Database error while deleting safety profile: {exc}"
            ) from exc
