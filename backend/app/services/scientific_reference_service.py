"""
ScientificReference business logic service.

All database operations for ScientificReference live here.
API routes should call this service instead of querying Prisma directly.

Usage from a route handler:

    from app.services.scientific_reference_service import ScientificReferenceService
    from app.database import db

    service = ScientificReferenceService(db)
    reference = await service.get_reference_by_id("some-uuid")
"""

from datetime import datetime

from prisma import Prisma
from prisma.models import ScientificReference

from app.core.exceptions import DomainError
from app.services.ingredient_service import IngredientNotFoundError


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScientificReferenceAlreadyExistsError(DomainError):
    """Raised when a reference with the same title and organization exists for an ingredient."""

    status_code = 409

    def __init__(self, title: str, organization: str) -> None:
        super().__init__(
            f"Scientific reference with title '{title}' "
            f"by organization '{organization}' already exists"
        )


class ScientificReferenceNotFoundError(DomainError):
    """Raised when a scientific reference cannot be found by the given criteria."""

    status_code = 404

    def __init__(self, detail: str = "Scientific reference not found") -> None:
        super().__init__(detail)


class InvalidPublicationYearError(DomainError):
    """Raised when the publication year is in the future."""

    status_code = 422

    def __init__(self, year: int) -> None:
        super().__init__(
            f"Publication year {year} is invalid — cannot be in the future"
        )


class InvalidSourceUrlError(DomainError):
    """Raised when the source URL is not a valid HTTP/HTTPS URL."""

    status_code = 422

    def __init__(self, url: str) -> None:
        super().__init__(f"Invalid source URL: '{url}' — must start with http:// or https://")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ScientificReferenceService:
    """Stateless service wrapping all ScientificReference CRUD operations.

    Instantiate once per request (or once at startup if the ``db``
    client is shared) and call its async methods.

        service = ScientificReferenceService(db)
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_reference(
        self,
        ingredient_id: str,
        title: str,
        organization: str,
        publication_year: int,
        evidence_summary: str,
        source_url: str,
    ) -> ScientificReference:
        """Create a new scientific reference for an ingredient.

        Validates that:
            1. The referenced Ingredient exists in the database.
            2. No reference with the same title and organization exists for this ingredient.
            3. The publication year is not in the future.
            4. The source URL is a valid HTTP/HTTPS URL.

        Args:
            ingredient_id:     UUID of the ingredient this reference supports.
            title:             Title of the scientific publication.
            organization:      Publishing organization or journal.
            publication_year:  Year the reference was published.
            evidence_summary:  Summary of the evidence presented.
            source_url:        URL to the original publication.

        Returns:
            The newly created ScientificReference record.

        Raises:
            IngredientNotFoundError:                    If the ingredient does not exist.
            ScientificReferenceAlreadyExistsError:      If the same title-organization
                                                        pair already exists for the ingredient.
            InvalidPublicationYearError:                If the publication year is in the future.
            InvalidSourceUrlError:                      If the source URL is not HTTP/HTTPS.
        """
        # ---- Validate the ingredient exists ----
        ingredient = await self._db.ingredient.find_unique(
            where={"id": ingredient_id}
        )
        if ingredient is None:
            raise IngredientNotFoundError(
                f"Ingredient with id '{ingredient_id}' not found"
            )

        # ---- Ensure no duplicate reference for this title-organization pair ----
        existing = await self._db.scientificreference.find_first(
            where={
                "ingredientId": ingredient_id,
                "title": title,
                "organization": organization,
            }
        )
        if existing is not None:
            raise ScientificReferenceAlreadyExistsError(title, organization)

        # ---- Validate publication year is not in the future ----
        current_year = datetime.now().year
        if publication_year > current_year:
            raise InvalidPublicationYearError(publication_year)

        # ---- Validate source URL is HTTP/HTTPS ----
        if not source_url.startswith(("http://", "https://")):
            raise InvalidSourceUrlError(source_url)

        # ---- Create the reference ----
        reference = await self._db.scientificreference.create(
            data={
                "ingredientId": ingredient_id,
                "title": title,
                "organization": organization,
                "publicationYear": publication_year,
                "evidenceSummary": evidence_summary,
                "sourceUrl": source_url,
            }
        )
        return reference

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_all_references(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ScientificReference]:
        """Return a paginated list of all scientific references.

        Args:
            skip:  Number of records to skip (for pagination).
            limit: Maximum number of records to return.

        Returns:
            A list of ScientificReference records (may be empty).
        """
        references = await self._db.scientificreference.find_many(
            skip=skip,
            take=limit,
        )
        return references

    async def get_reference_by_id(self, reference_id: str) -> ScientificReference:
        """Look up a single scientific reference by its UUID.

        Args:
            reference_id: The UUID of the scientific reference.

        Returns:
            The matching ScientificReference record.

        Raises:
            ScientificReferenceNotFoundError: If no reference has this ID.
        """
        reference = await self._db.scientificreference.find_unique(
            where={"id": reference_id}
        )
        if reference is None:
            raise ScientificReferenceNotFoundError(
                f"Scientific reference with id '{reference_id}' not found"
            )
        return reference

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_reference(self, reference_id: str) -> dict[str, str]:
        """Delete a scientific reference by its UUID.

        Args:
            reference_id: The UUID of the scientific reference to delete.

        Returns:
            A confirmation dict with the deleted reference's ID.

        Raises:
            ScientificReferenceNotFoundError: If no reference has this ID.
        """
        # Verify the reference exists before attempting deletion
        existing = await self._db.scientificreference.find_unique(
            where={"id": reference_id}
        )
        if existing is None:
            raise ScientificReferenceNotFoundError(
                f"Scientific reference with id '{reference_id}' not found"
            )

        await self._db.scientificreference.delete(where={"id": reference_id})
        return {
            "id": reference_id,
            "message": "Scientific reference deleted successfully",
        }
