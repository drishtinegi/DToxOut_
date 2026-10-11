"""
Ingredient business logic service.

All database operations for the Ingredient knowledge base live here.
API routes should call this service instead of querying Prisma directly.

The search engine supports seven lookup tiers with case-insensitive
matching:

1. Exact INCI name
2. Exact common name
3. Exact alias
4. Partial INCI match (substring)
5. Partial common name (substring)
6. Partial alias (substring)
7. Fuzzy match (difflib.SequenceMatcher, threshold 0.80)

Usage from a route handler::

    from app.services.ingredient_service import IngredientService
    from app.database import db

    service = IngredientService(db)
    ingredient = await service.get_ingredient_by_inci("Niacinamide")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Optional

from prisma import Prisma
from prisma.models import Ingredient

from app.core.exceptions import DomainError
from app.schemas.search import MatchedBy
from app.utils.ingredient_matcher import normalize_ingredient_name


# ---------------------------------------------------------------------------
# Prisma ``include`` payload shared by every search query.
# Eager-loads all relations the API layer needs so we never trigger
# lazy-load N+1 queries.
# ---------------------------------------------------------------------------

_RELATION_INCLUDE: dict[str, Any] = {
    "safetyProfile": True,
    "aliases": True,
    "benefits": True,
    "category": True,
    "regulations": True,
    "scientificReferences": True,
}

_FUZZY_THRESHOLD: float = 0.80
_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IngredientNotFoundError(DomainError):
    """Raised when an ingredient cannot be found by the given criteria."""

    status_code = 404

    def __init__(self, detail: str = "Ingredient not found") -> None:
        super().__init__(detail)


class IngredientAlreadyExistsError(DomainError):
    """Raised when creating an ingredient with a duplicate INCI name."""

    status_code = 409

    def __init__(self, inci_name: str) -> None:
        super().__init__(f"Ingredient with INCI name '{inci_name}' already exists")


class IngredientSearchNotFoundError(DomainError):
    """Raised when a search query matches no ingredient."""

    status_code = 404

    def __init__(self, query: str) -> None:
        super().__init__(f"Ingredient not found for query '{query}'")


# ---------------------------------------------------------------------------
# Internal value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """Value object returned by :meth:`IngredientService.search_ingredient`.

    Carries both the matched :class:`Ingredient` record and metadata
    about *how* the match was produced so the API layer can populate
    ``matched_by`` and ``matched_value`` without re-querying.

    Attributes:
        ingredient: The fully-loaded Prisma :class:`Ingredient` record
            (including safety profile, benefits, aliases, and category).
        matched_by: Which knowledge-base field produced the match.
        matched_value: The actual text value that was matched.
    """

    ingredient: Ingredient
    matched_by: MatchedBy
    matched_value: str


@dataclass(frozen=True)
class BulkSearchSummaryData:
    """Aggregate counts for a bulk search operation.

    Attributes:
        total_requested: Number of unique ingredient names queried
            (duplicates removed).
        found: Number of unique ingredients that matched a record.
        not_found: Number of unique ingredients that did not match.
    """

    total_requested: int
    found: int
    not_found: int


@dataclass(frozen=True)
class BulkSearchResult:
    """Value object returned by :meth:`IngredientService.search_multiple_ingredients`.

    Attributes:
        found: :class:`SearchResult` entries in request order.
        not_found: Original (pre-normalised) names that matched nothing.
        summary: Aggregate counts for this bulk operation.
    """

    found: list[SearchResult]
    not_found: list[str]
    summary: BulkSearchSummaryData


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IngredientService:
    """Stateless service wrapping all Ingredient CRUD operations.

    Instantiate once per request (or once at startup if the ``db``
    client is shared) and call its async methods.

    Example::

        service = IngredientService(db)
        ingredient = await service.get_ingredient_by_id("some-uuid")
    """

    def __init__(self, db: Prisma) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_ingredient(
        self,
        inci_name: str,
        description: str,
        function: str,
        safety_rating: float,
        evidence_level: str,
        common_name: Optional[str] = None,
        category_id: Optional[str] = None,
    ) -> Ingredient:
        """Create a new ingredient in the knowledge base.

        Args:
            inci_name: Official INCI name (must be unique).
                e.g. ``"Niacinamide"``.
            description: Human-readable description of the ingredient.
            function: Cosmetic function / purpose.
                e.g. ``"Skin conditioning"``.
            safety_rating: Numeric safety rating on a 0\u201310 scale
                (higher = safer).
            evidence_level: One of ``LOW``, ``MODERATE``, ``HIGH``,
                ``VERY_HIGH``.
            common_name: Optional everyday / trade name.
                e.g. ``"Vitamin B3"``.
            category_id: Optional UUID of an :class:`IngredientCategory`.

        Returns:
            The newly created :class:`Ingredient` record.

        Raises:
            IngredientAlreadyExistsError: If an ingredient with the same
                INCI name already exists.

        Example::

            ingredient = await service.create_ingredient(
                inci_name="Niacinamide",
                description="Form of vitamin B3",
                function="Skin conditioning",
                safety_rating=9.0,
                evidence_level="HIGH",
                common_name="Vitamin B3",
            )
        """
        existing = await self._db.ingredient.find_unique(
            where={"inciName": inci_name}
        )
        if existing:
            raise IngredientAlreadyExistsError(inci_name)

        ingredient = await self._db.ingredient.create(
            data={
                "inciName": inci_name,
                "description": description,
                "function": function,
                "safetyRating": safety_rating,
                "evidenceLevel": evidence_level,
                **({"commonName": common_name} if common_name else {}),
                **({"categoryId": category_id} if category_id else {}),
            }
        )
        return ingredient

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_ingredient_by_inci(self, inci_name: str) -> Ingredient:
        """Look up a single ingredient by its INCI name.

        Args:
            inci_name: The INCI name to search for (case-insensitive
                match at the database level).

        Returns:
            The matching :class:`Ingredient` record.

        Raises:
            IngredientNotFoundError: If no ingredient has this INCI name.

        Example::

            ingredient = await service.get_ingredient_by_inci("Niacinamide")
        """
        ingredient = await self._db.ingredient.find_unique(
            where={"inciName": inci_name}
        )
        if ingredient is None:
            raise IngredientNotFoundError(
                f"Ingredient '{inci_name}' not found"
            )
        return ingredient

    async def get_ingredient_by_id(self, ingredient_id: str) -> Ingredient:
        """Look up a single ingredient by its UUID.

        Args:
            ingredient_id: The UUID of the ingredient.

        Returns:
            The matching :class:`Ingredient` record.

        Raises:
            IngredientNotFoundError: If no ingredient has this ID.

        Example::

            ingredient = await service.get_ingredient_by_id(
                "d290f1ee-6c54-4b01-90e6-d701748f0851"
            )
        """
        ingredient = await self._db.ingredient.find_unique(
            where={"id": ingredient_id}
        )
        if ingredient is None:
            raise IngredientNotFoundError(
                f"Ingredient with id '{ingredient_id}' not found"
            )
        return ingredient

    async def get_ingredient_knowledge(
        self,
        ingredient_id: str,
    ) -> Ingredient:
        """Load a single ingredient with all related entities for knowledge assembly.

        Eager-loads the following relations via Prisma ``include``:

        * ``category`` — the assigned ingredient category
        * ``safetyProfile`` — detailed safety breakdown
        * ``aliases`` — alternative names / trade names
        * ``benefits`` — known skin benefits
        * ``regulations`` — regulatory status by country
        * ``scientificReferences`` — supporting publications

        This method is used by the Knowledge Engine endpoint.  The
        returned Prisma record is intended to be passed to
        :meth:`KnowledgeBuilder.build` for response assembly.

        Args:
            ingredient_id: The UUID of the ingredient to load.

        Returns:
            A fully-loaded :class:`Ingredient` record with all nested
            relations.

        Raises:
            IngredientNotFoundError: If no ingredient has this ID.

        Example::

            ingredient = await service.get_ingredient_knowledge(
                "d290f1ee-6c54-4b01-90e6-d701748f0851"
            )
            response = KnowledgeBuilder.build(ingredient)
        """
        ingredient = await self._db.ingredient.find_unique(
            where={"id": ingredient_id},
            include=_RELATION_INCLUDE,
        )
        if ingredient is None:
            raise IngredientNotFoundError(
                f"Ingredient with id '{ingredient_id}' not found"
            )
        return ingredient

    async def get_all_ingredients(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Ingredient]:
        """Return a paginated list of all ingredients.

        Results are ordered by ``createdAt`` descending (newest first).

        Args:
            skip: Number of records to skip (for pagination).
                Defaults to ``0``.
            limit: Maximum number of records to return.
                Defaults to ``100``.

        Returns:
            A list of :class:`Ingredient` records (may be empty).

        Example::

            first_page = await service.get_all_ingredients(skip=0, limit=20)
            second_page = await service.get_all_ingredients(skip=20, limit=20)
        """
        ingredients = await self._db.ingredient.find_many(
            skip=skip,
            take=limit,
            order={"createdAt": "desc"},
        )
        return ingredients

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_ingredient(self, query: str) -> SearchResult:
        """Search for a single ingredient by name or alias.

        The query is normalised (whitespace collapsed, trimmed) and then
        matched case-insensitively against the knowledge base using the
        following priority order:

        1. **Exact INCI name** — ``Ingredient.inciName``
        2. **Exact common name** — ``Ingredient.commonName``
        3. **Exact alias** — ``IngredientAlias.alias``
        4. **Partial INCI match** — query is a substring of ``inciName``
           or vice versa
        5. **Partial common name** — query is a substring of ``commonName``
           or vice versa
        6. **Partial alias** — query is a substring of an alias or vice
           versa
        7. **Fuzzy match** — ``SequenceMatcher`` ratio above the
           configured threshold (default 0.80)

        Exact matches (tiers 1–3) are resolved via indexed database
        queries for maximum speed.  Partial and fuzzy matches (tiers 4–7)
        are resolved in memory after fetching all ingredients with their
        aliases, which enables proper ranking across candidates.

        All queries eagerly load the safety profile, benefits, aliases,
        and category relations (via ``_RELATION_INCLUDE``) so the API
        layer can return them without additional round-trips.

        Args:
            query: Free-text search string. Leading/trailing whitespace
                is removed and internal runs of whitespace are collapsed
                to a single space before matching.

        Returns:
            A :class:`SearchResult` carrying the matched
            :class:`Ingredient` plus ``matched_by`` / ``matched_value``
            metadata.

        Raises:
            IngredientSearchNotFoundError: If no ingredient matches the
                query across all seven lookup strategies.

        Example::

            result = await service.search_ingredient("Niacinamide")
            # result.matched_by == MatchedBy.INCI_NAME

            result = await service.search_ingredient("Niacinmid")
            # Fuzzy match — result.matched_by == MatchedBy.INCI_NAME
        """
        start_time = time.monotonic()
        normalised = self._normalise_query(query)
        normalised_lower = normalised.lower()

        # --- 1. Exact INCI name (case-insensitive) ---
        ingredient = await self._db.ingredient.find_first(
            where={
                "inciName": {
                    "equals": normalised,
                    "mode": "insensitive",
                }
            },
            include=_RELATION_INCLUDE,
        )

        if ingredient is not None:
            self._log_search(query, "EXACT_INCI", 1.0, start_time)
            return SearchResult(
                ingredient=ingredient,
                matched_by=MatchedBy.INCI_NAME,
                matched_value=ingredient.inciName,
            )

        # --- 2. Exact common name (case-insensitive) ---
        ingredient = await self._db.ingredient.find_first(
            where={
                "commonName": {
                    "equals": normalised,
                    "mode": "insensitive",
                }
            },
            include=_RELATION_INCLUDE,
        )

        if ingredient is not None:
            self._log_search(query, "EXACT_COMMON", 1.0, start_time)
            return SearchResult(
                ingredient=ingredient,
                matched_by=MatchedBy.COMMON_NAME,
                matched_value=ingredient.commonName or "",
            )

        # --- 3. Exact alias (case-insensitive) ---
        alias_record = await self._db.ingredientalias.find_first(
            where={
                "alias": {
                    "equals": normalised,
                    "mode": "insensitive",
                }
            },
            include={"ingredient": {"include": _RELATION_INCLUDE}},
        )
        if alias_record is not None and alias_record.ingredient is not None:
            self._log_search(query, "EXACT_ALIAS", 1.0, start_time)
            return SearchResult(
                ingredient=alias_record.ingredient,
                matched_by=MatchedBy.ALIAS,
                matched_value=alias_record.alias,
            )

        # --- 4–7. Partial and fuzzy matches (in-memory) ---
        result = await self._search_advanced(
            normalised_lower, start_time, query,
        )
        if result is not None:
            return result

        self._log_search(query, "NONE", 0.0, start_time)
        raise IngredientSearchNotFoundError(normalised)

    async def search_multiple_ingredients(
        self,
        queries: list[str],
    ) -> BulkSearchResult:
        """Search for multiple ingredients, deduplicating and preserving order.

        Each query is normalised and de-duplicated *before* any database
        call.  For each unique query the method delegates to
        :meth:`search_ingredient`, catching
        :class:`IngredientSearchNotFoundError` so that a single missing
        ingredient never blocks the rest.

        A per-request cache (``dict[str, SearchResult | None]``) ensures
        that identical names only touch the database once, even when they
        appear multiple times in the input list.

        Args:
            queries: List of ingredient names (may contain duplicates).
                Each entry is trimmed before lookup.

        Returns:
            A :class:`BulkSearchResult` containing:

            * ``found``     \u2013 list of :class:`SearchResult` in request order
            * ``not_found`` \u2013 list of original names that matched nothing
            * ``summary``   \u2013 :class:`BulkSearchSummaryData` with counts

        Example::

            result = await service.search_multiple_ingredients(
                ["Niacinamide", "Water", "Niacinamide"]
            )
            # result.summary.total_requested == 2  (deduplicated)
            # len(result.found) + len(result.not_found) == 2
        """
        # Normalise all queries up-front.
        normalised_pairs = [
            (original, self._normalise_query(original))
            for original in queries
        ]

        # Deduplicate while preserving first-occurrence order.
        seen: set[str] = set()
        unique_pairs: list[tuple[str, str]] = []
        for original, norm in normalised_pairs:
            if norm not in seen:
                seen.add(norm)
                unique_pairs.append((original, norm))

        # Cache: normalised name -> SearchResult or None (not found).
        cache: dict[str, Optional[SearchResult]] = {}

        for _original, norm in unique_pairs:
            try:
                result = await self.search_ingredient(norm)
                cache[norm] = result
            except IngredientSearchNotFoundError:
                cache[norm] = None

        # Build output in original request order (including duplicates).
        found: list[SearchResult] = []
        not_found: list[str] = []
        for _original, norm in normalised_pairs:
            cached = cache[norm]
            if cached is not None:
                found.append(cached)
            else:
                not_found.append(_original)

        total_unique = len(unique_pairs)
        total_found = sum(1 for v in cache.values() if v is not None)

        return BulkSearchResult(
            found=found,
            not_found=not_found,
            summary=BulkSearchSummaryData(
                total_requested=total_unique,
                found=total_found,
                not_found=total_unique - total_found,
            ),
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_ingredient(self, ingredient_id: str) -> dict[str, str]:
        """Delete an ingredient by its UUID.

        Args:
            ingredient_id: The UUID of the ingredient to delete.

        Returns:
            A confirmation dict containing the deleted ingredient's ID
            and a success message.

        Raises:
            IngredientNotFoundError: If no ingredient has this ID.

        Example::

            result = await service.delete_ingredient(
                "d290f1ee-6c54-4b01-90e6-d701748f0851"
            )
            # {"id": "d290f1ee-...", "message": "Ingredient deleted successfully"}
        """
        existing = await self._db.ingredient.find_unique(
            where={"id": ingredient_id}
        )
        if existing is None:
            raise IngredientNotFoundError(
                f"Ingredient with id '{ingredient_id}' not found"
            )

        await self._db.ingredient.delete(where={"id": ingredient_id})
        return {
            "id": ingredient_id,
            "message": "Ingredient deleted successfully",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _search_advanced(
        self,
        normalised_lower: str,
        start_time: float,
        original_query: str,
    ) -> Optional[SearchResult]:
        """Search for partial and fuzzy matches across all ingredients.

        Attempts DB-side partial matching first (tiers 4–6) to avoid
        loading the full table.  Only falls back to a full table scan
        for fuzzy matching (tier 7) when no partial matches exist.

        Partial matches always take precedence over fuzzy matches.
        Within partial matches, lower tier numbers win (INCI > common >
        alias).  Within the same tier, the highest similarity score wins.

        Args:
            normalised_lower: Lowercase, whitespace-collapsed search query.
            start_time: :func:`time.monotonic` timestamp for logging.
            original_query: The original user-provided query for logging.

        Returns:
            A :class:`SearchResult` if a match is found, or ``None`` if
            no partial or fuzzy match exceeds the threshold.
        """
        best_partial: Optional[tuple[Ingredient, MatchedBy, str]] = None
        best_partial_tier: int = 100
        best_partial_score: float = -1.0

        def _update_partial(
            ing: Ingredient,
            match_type: MatchedBy,
            value: str,
            tier: int,
            score: float,
        ) -> None:
            nonlocal best_partial, best_partial_tier, best_partial_score
            if tier < best_partial_tier or (
                tier == best_partial_tier and score > best_partial_score
            ):
                best_partial = (ing, match_type, value)
                best_partial_tier = tier
                best_partial_score = score

        # --- Tier 4: Partial INCI name (DB-side) ---
        inci_candidates = await self._db.ingredient.find_many(
            where={
                "inciName": {"contains": normalised_lower, "mode": "insensitive"},
            },
            include=_RELATION_INCLUDE,
        )

        for ing in inci_candidates:
            if ing.inciName:
                value_lower = ing.inciName.lower()
                score = self._compute_similarity(normalised_lower, value_lower)
                is_partial = (
                    normalised_lower in value_lower
                    or value_lower in normalised_lower
                )
                if is_partial:
                    _update_partial(ing, MatchedBy.INCI_NAME, ing.inciName, 4, score)

        # --- Tier 5: Partial common name (DB-side) ---
        if best_partial_tier > 5:
            common_candidates = await self._db.ingredient.find_many(
                where={
                    "commonName": {"contains": normalised_lower, "mode": "insensitive"},
                },
                include=_RELATION_INCLUDE,
            )

            for ing in common_candidates:
                if ing.commonName:
                    value_lower = ing.commonName.lower()
                    score = self._compute_similarity(normalised_lower, value_lower)
                    is_partial = (
                        normalised_lower in value_lower
                        or value_lower in normalised_lower
                    )
                    if is_partial:
                        _update_partial(ing, MatchedBy.COMMON_NAME, ing.commonName, 5, score)

        # --- Tier 6: Partial alias (DB-side) ---
        if best_partial_tier > 6:
            alias_candidates = await self._db.ingredientalias.find_many(
                where={
                    "alias": {"contains": normalised_lower, "mode": "insensitive"},
                },
                include={"ingredient": {"include": _RELATION_INCLUDE}},
            )

            for alias_record in alias_candidates:
                if alias_record.ingredient is not None:
                    ing = alias_record.ingredient
                    value_lower = alias_record.alias.lower()
                    score = self._compute_similarity(normalised_lower, value_lower)
                    is_partial = (
                        normalised_lower in value_lower
                        or value_lower in normalised_lower
                    )
                    if is_partial:
                        _update_partial(ing, MatchedBy.ALIAS, alias_record.alias, 6, score)

        # Return the best partial match if found (partial always beats fuzzy).
        if best_partial is not None:
            ing, match_type, value = best_partial
            self._log_search(
                original_query, "PARTIAL", best_partial_score, start_time,
            )
            return SearchResult(
                ingredient=ing,
                matched_by=match_type,
                matched_value=value,
            )

        # --- Tier 7: Fuzzy match (full table scan, aliases needed) ---
        all_ingredients = await self._db.ingredient.find_many(
            include={"aliases": True},
        )

        best_fuzzy: Optional[tuple[Ingredient, MatchedBy, str]] = None
        best_fuzzy_score: float = _FUZZY_THRESHOLD

        for ing in all_ingredients:
            if ing.inciName:
                value_lower = ing.inciName.lower()
                score = self._compute_similarity(normalised_lower, value_lower)
                is_partial = (
                    normalised_lower in value_lower
                    or value_lower in normalised_lower
                )
                if not is_partial and score > best_fuzzy_score:
                    best_fuzzy = (ing, MatchedBy.INCI_NAME, ing.inciName)
                    best_fuzzy_score = score

            if ing.commonName:
                value_lower = ing.commonName.lower()
                score = self._compute_similarity(normalised_lower, value_lower)
                is_partial = (
                    normalised_lower in value_lower
                    or value_lower in normalised_lower
                )
                if not is_partial and score > best_fuzzy_score:
                    best_fuzzy = (ing, MatchedBy.COMMON_NAME, ing.commonName)
                    best_fuzzy_score = score

            for alias in (ing.aliases or []):
                value_lower = alias.alias.lower()
                score = self._compute_similarity(normalised_lower, value_lower)
                is_partial = (
                    normalised_lower in value_lower
                    or value_lower in normalised_lower
                )
                if not is_partial and score > best_fuzzy_score:
                    best_fuzzy = (ing, MatchedBy.ALIAS, alias.alias)
                    best_fuzzy_score = score

        if best_fuzzy is not None:
            ing, match_type, value = best_fuzzy
            self._log_search(
                original_query, "FUZZY", best_fuzzy_score, start_time,
            )
            return SearchResult(
                ingredient=ing,
                matched_by=match_type,
                matched_value=value,
            )

        return None

    @staticmethod
    def _compute_similarity(a: str, b: str) -> float:
        """Compute similarity ratio between two strings.

        Uses Python's :class:`difflib.SequenceMatcher` to produce a ratio
        between 0.0 (no similarity) and 1.0 (identical strings).

        Args:
            a: First string (should be lowercase).
            b: Second string (should be lowercase).

        Returns:
            Similarity ratio between 0.0 and 1.0.

        Example::

            >>> IngredientService._compute_similarity(
            ...     "niacinamide", "niacinamide",
            ... )
            1.0
        """
        return SequenceMatcher(None, a, b).ratio()

    @staticmethod
    def _log_search(
        query: str,
        match_type: str,
        score: float,
        start_time: float,
    ) -> None:
        """Log search metrics for observability.

        Emits a structured log line containing the original query, the
        match type (e.g. ``EXACT_INCI``, ``PARTIAL``, ``FUZZY``), the
        similarity score, and the elapsed wall-clock time.

        Args:
            query: The original user-provided search query.
            match_type: Label indicating how the match was produced.
            score: Similarity score (1.0 for exact, 0.0–1.0 otherwise).
            start_time: :func:`time.monotonic` timestamp from the caller.
        """
        elapsed_ms = (time.monotonic() - start_time) * 1000
        _LOGGER.info(
            "search query=%s match_type=%s score=%.4f time=%.1fms",
            query,
            match_type,
            score,
            elapsed_ms,
        )

    @staticmethod
    def _normalise_query(raw: str) -> str:
        """Standardize a raw search string using normalize_ingredient_name.

        Args:
            raw: The original user-provided search string.

        Returns:
            A lowercased, trimmed, punctuation-free string.
        """
        return normalize_ingredient_name(raw)
