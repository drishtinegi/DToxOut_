"""
Regulation business logic service.

All database operations for Regulation live here.
API routes should call this service instead of querying Prisma directly.

Usage from a route handler:

    from app.services.regulation_service import RegulationService
    from app.database import db

    service = RegulationService(db)
    regulation = await service.get_regulation_by_id("some-uuid")
"""

from prisma import Prisma
from prisma.models import Regulation

from app.core.exceptions import DomainError
from app.services.ingredient_service import IngredientNotFoundError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class RegulationAlreadyExistsError(DomainError):
    """Raised when a regulation for the same ingredient-country pair exists."""

    status_code = 409

    def __init__(self, ingredient_id: str, country: str) -> None:
        super().__init__(
            f"Regulation already exists for ingredient '{ingredient_id}' "
            f"in country '{country}'"
        )


class RegulationNotFoundError(DomainError):
    """Raised when a regulation cannot be found by the given criteria."""

    status_code = 404

    def __init__(self, detail: str = "Regulation not found") -> None:
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class RegulationService:
    """Stateless service wrapping all Regulation CRUD operations.

    Instantiate once per request (or once at startup if the ``db``
    client is shared) and call its async methods.

        service = RegulationService(db)
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_regulation(
        self,
        ingredient_id: str,
        country: str,
        regulatory_status: str,
        restriction_details: str,
        source: str,
        jurisdiction: str | None = None,
        source_organization: str | None = None,
        source_url: str | None = None,
        retrieved_date=None,
        effective_date=None,
        source_type: str = "REGULATORY_LIST",
        verification_status: str = "UNVERIFIED",
        reviewer_notes: str | None = None,
        source_document_id: str | None = None,
        product_category: str | None = None,
        concentration_limit: str | None = None,
    ) -> Regulation:
        """Create a new regulation for an ingredient in a country.

        Validates that:
            1. The referenced Ingredient exists in the database.
            2. No regulation already exists for this ingredient-country pair.

        Returns:
            The newly created Regulation record.

        Raises:
            IngredientNotFoundError:       If the ingredient does not exist.
            RegulationAlreadyExistsError:  If the same ingredient-country
                combination already has a regulation.
        """
        # ---- Validate the ingredient exists ----
        ingredient = await self._db.ingredient.find_unique(
            where={"id": ingredient_id}
        )
        if ingredient is None:
            raise IngredientNotFoundError(
                f"Ingredient with id '{ingredient_id}' not found"
            )

        # ---- Ensure no duplicate regulation for this ingredient-country pair ----
        where_clause = {
            "ingredientId": ingredient_id,
            "country": country,
        }
        if jurisdiction is not None:
            where_clause["jurisdiction"] = jurisdiction
        if product_category is not None:
            where_clause["productCategory"] = product_category

        existing = await self._db.regulation.find_first(where=where_clause)
        if existing is not None:
            raise RegulationAlreadyExistsError(ingredient_id, country)

        # ---- Create the regulation ----
        data = {
            "ingredientId": ingredient_id,
            "country": country,
            "regulatoryStatus": regulatory_status,
            "restrictionDetails": restriction_details,
            "source": source,
            "sourceType": source_type,
            "verificationStatus": verification_status,
        }
        if jurisdiction is not None:
            data["jurisdiction"] = jurisdiction
        if source_organization is not None:
            data["sourceOrganization"] = source_organization
        if source_url is not None:
            data["sourceUrl"] = source_url
        if retrieved_date is not None:
            data["retrievedDate"] = retrieved_date
        if effective_date is not None:
            data["effectiveDate"] = effective_date
        if reviewer_notes is not None:
            data["reviewerNotes"] = reviewer_notes
        if source_document_id is not None:
            data["sourceDocumentId"] = source_document_id
        if product_category is not None:
            data["productCategory"] = product_category
        if concentration_limit is not None:
            data["concentrationLimit"] = concentration_limit

        regulation = await self._db.regulation.create(data=data)
        return regulation

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_all_regulations(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Regulation]:
        """Return a paginated list of all regulations.

        Args:
            skip:  Number of records to skip (for pagination).
            limit: Maximum number of records to return.

        Returns:
            A list of Regulation records (may be empty).
        """
        regulations = await self._db.regulation.find_many(
            skip=skip,
            take=limit,
        )
        return regulations

    async def get_regulation_by_id(self, regulation_id: str) -> Regulation:
        """Look up a single regulation by its UUID.

        Args:
            regulation_id: The UUID of the regulation.

        Returns:
            The matching Regulation record.

        Raises:
            RegulationNotFoundError: If no regulation has this ID.
        """
        regulation = await self._db.regulation.find_unique(
            where={"id": regulation_id}
        )
        if regulation is None:
            raise RegulationNotFoundError(
                f"Regulation with id '{regulation_id}' not found"
            )
        return regulation

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_regulation(self, regulation_id: str) -> dict[str, str]:
        """Delete a regulation by its UUID.

        Args:
            regulation_id: The UUID of the regulation to delete.

        Returns:
            A confirmation dict with the deleted regulation's ID.

        Raises:
            RegulationNotFoundError: If no regulation has this ID.
        """
        # Verify the regulation exists before attempting deletion
        existing = await self._db.regulation.find_unique(
            where={"id": regulation_id}
        )
        if existing is None:
            raise RegulationNotFoundError(
                f"Regulation with id '{regulation_id}' not found"
            )

        await self._db.regulation.delete(where={"id": regulation_id})
        return {
            "id": regulation_id,
            "message": "Regulation deleted successfully",
        }
