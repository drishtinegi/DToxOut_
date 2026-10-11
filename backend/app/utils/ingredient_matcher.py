import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Optional

from app.schemas.scan import MatchType


# ---------------------------------------------------------------------------
# Compiled patterns (shared across calls for performance)
# ---------------------------------------------------------------------------

# Characters to strip: commas, semicolons, periods, tabs, newlines.
_REMOVE_RE = re.compile(r"[,;.\t\n\r]")

# Two or more whitespace characters in a row.
_MULTI_SPACE_RE = re.compile(r" {2,}")

_FUZZY_MIN_THRESHOLD = 0.85
_FUZZY_MIN_LENGTH_RATIO = 0.70

# Short generic terms that must not fuzzy match unrelated full names
_GENERIC_SHORT_TERMS = {
    "acid",
    "oil",
    "extract",
    "water",
    "juice",
    "butter",
    "wax",
    "gum",
    "powder",
    "root",
    "leaf",
    "flower",
    "seed",
}


# ---------------------------------------------------------------------------
# Data classes & Matcher abstraction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchResult:
    """Result of attempting to match an input string to an ingredient record.

    Attributes:
        ingredient: The Prisma Ingredient model or None if unmatched.
        match_type: Lookup tier used to produce the match.
        match_confidence: Numeric confidence (0.0 to 1.0).
        manual_confirmation_recommended: True if fuzzy or low confidence.
        matched_value: The text string in the database that matched.
        query_term_str: Original query term string (optional override).
    """

    ingredient: Optional[Any]
    match_type: MatchType
    match_confidence: float
    manual_confirmation_recommended: bool
    matched_value: str
    query_term_str: Optional[str] = None

    @property
    def query_term(self) -> str:
        return self.query_term_str or self.matched_value

    @property
    def matched_inci(self) -> Optional[str]:
        if self.ingredient:
            return getattr(self.ingredient, "inciName", None) or getattr(self.ingredient, "inci_name", None)
        return None

    @property
    def confidence_score(self) -> float:
        return self.match_confidence

    @property
    def reason(self) -> str:
        if self.match_type == MatchType.EXACT_INCI:
            return "Exact INCI match found in knowledge base."
        elif self.match_type == MatchType.EXACT_ALIAS:
            return "Exact alias match found in knowledge base."
        elif self.match_type == MatchType.EXACT_COMMON_NAME:
            return "Exact common-name match found in knowledge base."
        elif self.match_type == MatchType.FUZZY:
            return f"High-confidence fuzzy match ({int(self.match_confidence * 100)}%)."
        return "Term not recognized in knowledge base."


class DummyIngredient:
    """Helper dummy class for in-memory testing of IngredientMatcher."""
    def __init__(self, inci_name: str, common_name: Optional[str] = None, aliases: Optional[list[str]] = None) -> None:
        self.inciName = inci_name
        self.commonName = common_name
        self.aliases = [{"alias": a} if isinstance(a, str) else a for a in (aliases or [])]


class IngredientMatcher:
    """Unified, focused matching engine for DToxOut ingredients.

    Implements strict matching order:
    1. Exact normalized INCI name (EXACT_INCI)
    2. Exact normalized alias (EXACT_ALIAS)
    3. Exact normalized common name (EXACT_COMMON_NAME)
    4. Carefully bounded fuzzy matching (FUZZY, ratio >= 0.85)
    5. Otherwise UNKNOWN
    """

    def __init__(self, candidates: Optional[list[Any]] = None) -> None:
        self.candidates: list[Any] = candidates or []

    def add_ingredient(
        self,
        inci_name: str,
        common_name: Optional[str] = None,
        aliases: Optional[list[str]] = None
    ) -> None:
        """Add an ingredient record to in-memory matcher candidates."""
        self.candidates.append(DummyIngredient(inci_name, common_name, aliases))

    async def load_knowledge_base(self, db: Any) -> None:
        """Load all ingredients from Prisma database into candidate pool."""
        self.candidates = await db.ingredient.find_many(
            include={
                "safetyProfile": True,
                "aliases": True,
                "regulations": True,
                "scientificReferences": True,
            }
        )

    def match_batch(self, queries: list[str]) -> list[MatchResult]:
        """Match a batch of raw or cleaned query strings against loaded candidates."""
        results = []
        for q in queries:
            res = self.match_single(q, self.candidates)
            # Retain original query term in MatchResult
            results.append(
                MatchResult(
                    ingredient=res.ingredient,
                    match_type=res.match_type,
                    match_confidence=res.match_confidence,
                    manual_confirmation_recommended=res.manual_confirmation_recommended,
                    matched_value=res.matched_value,
                    query_term_str=q,
                )
            )
        return results


    @staticmethod
    def match_single(
        query: str,
        candidates: list[Any],
    ) -> MatchResult:
        """Match a single normalized input query against a list of candidate ingredients.

        Args:
            query: Raw or normalized query string.
            candidates: List of Prisma Ingredient records (with safetyProfile,
                aliases, regulations, scientificReferences eagerly loaded).

        Returns:
            A populated MatchResult.
        """
        norm_query = normalize_ingredient_name(query)
        if not norm_query:
            return MatchResult(
                ingredient=None,
                match_type=MatchType.UNKNOWN,
                match_confidence=0.0,
                manual_confirmation_recommended=False,
                matched_value=query,
            )

        # Tier 1 — Exact INCI name
        for ing in candidates:
            inci_name = getattr(ing, "inciName", "") or ""
            if normalize_ingredient_name(inci_name) == norm_query:
                return MatchResult(
                    ingredient=ing,
                    match_type=MatchType.EXACT_INCI,
                    match_confidence=1.0,
                    manual_confirmation_recommended=False,
                    matched_value=inci_name,
                )

        # Tier 2 — Exact Alias
        for ing in candidates:
            aliases = getattr(ing, "aliases", []) or []
            for alias_obj in aliases:
                alias_str = (
                    getattr(alias_obj, "alias", "")
                    if hasattr(alias_obj, "alias")
                    else str(alias_obj)
                )
                if normalize_ingredient_name(alias_str) == norm_query:
                    return MatchResult(
                        ingredient=ing,
                        match_type=MatchType.EXACT_ALIAS,
                        match_confidence=1.0,
                        manual_confirmation_recommended=False,
                        matched_value=alias_str,
                    )

        # Tier 3 — Exact Common Name
        for ing in candidates:
            common_name = getattr(ing, "commonName", "") or ""
            if common_name and normalize_ingredient_name(common_name) == norm_query:
                return MatchResult(
                    ingredient=ing,
                    match_type=MatchType.EXACT_COMMON_NAME,
                    match_confidence=1.0,
                    manual_confirmation_recommended=False,
                    matched_value=common_name,
                )

        # Tier 4 — Carefully bounded fuzzy matching
        if norm_query in _GENERIC_SHORT_TERMS:
            # Generic short terms must not match unrelated full names (e.g. "acid" matching "Salicylic Acid")
            return MatchResult(
                ingredient=None,
                match_type=MatchType.UNKNOWN,
                match_confidence=0.0,
                manual_confirmation_recommended=False,
                matched_value=query,
            )

        best_fuzzy_ing: Optional[Any] = None
        best_fuzzy_val: str = ""
        best_ratio: float = 0.0

        for ing in candidates:
            targets: list[str] = []
            inci_name = getattr(ing, "inciName", "") or ""
            if inci_name:
                targets.append(inci_name)

            common_name = getattr(ing, "commonName", "") or ""
            if common_name:
                targets.append(common_name)

            aliases = getattr(ing, "aliases", []) or []
            for alias_obj in aliases:
                alias_str = (
                    getattr(alias_obj, "alias", "")
                    if hasattr(alias_obj, "alias")
                    else str(alias_obj)
                )
                if alias_str:
                    targets.append(alias_str)

            for target in targets:
                norm_target = normalize_ingredient_name(target)
                if not norm_target:
                    continue

                len_ratio = min(len(norm_query), len(norm_target)) / max(
                    len(norm_query), len(norm_target)
                )
                if len_ratio < _FUZZY_MIN_LENGTH_RATIO:
                    continue

                ratio = SequenceMatcher(None, norm_query, norm_target).ratio()
                if ratio >= _FUZZY_MIN_THRESHOLD and ratio > best_ratio:
                    best_ratio = ratio
                    best_fuzzy_ing = ing
                    best_fuzzy_val = target

        if best_fuzzy_ing is not None:
            return MatchResult(
                ingredient=best_fuzzy_ing,
                match_type=MatchType.FUZZY,
                match_confidence=round(best_ratio, 2),
                manual_confirmation_recommended=True,
                matched_value=best_fuzzy_val,
            )

        # Tier 5 — Unknown
        return MatchResult(
            ingredient=None,
            match_type=MatchType.UNKNOWN,
            match_confidence=0.0,
            manual_confirmation_recommended=False,
            matched_value=query,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize_ingredient_name(name: str) -> str:
    """Convert an ingredient name into a standardized searchable format.

    The transformation pipeline:

    1. Strip leading / trailing whitespace.
    2. Convert to lowercase.
    3. Remove commas, semicolons, periods, tabs, and newlines.
    4. Collapse multiple spaces into a single space.

    Numbers, hyphens, and parentheses are preserved.

    Args:
        name: Raw ingredient name (may contain leading/trailing
              whitespace, mixed case, punctuation, etc.).

    Returns:
        A lowercased, trimmed, punctuation-free string.

    Examples::

        >>> normalize_ingredient_name(" Niacinamide ")
        'niacinamide'

        >>> normalize_ingredient_name("NIACINAMIDE")
        'niacinamide'

        >>> normalize_ingredient_name("Sodium  Hyaluronate")
        'sodium hyaluronate'

        >>> normalize_ingredient_name("Panthenol.")
        'panthenol'

        >>> normalize_ingredient_name("Glycerin,")
        'glycerin'

        >>> normalize_ingredient_name("Hydroxyethyl-cellulose")
        'hydroxyethyl-cellulose'

        >>> normalize_ingredient_name("(Vitamin E)")
        '(vitamin e)'
    """
    result = name.strip()
    result = result.lower()
    result = _REMOVE_RE.sub("", result)
    result = _MULTI_SPACE_RE.sub(" ", result)
    return result


def normalize_ingredient_list(ingredients: list[str]) -> list[str]:
    """Normalize every ingredient name in a list.

    Ordering is preserved.  Empty strings and strings that become empty
    after normalization are silently dropped.

    Args:
        ingredients: A list of raw ingredient name strings.

    Returns:
        A new list containing only the non-empty normalized names.

    Examples::

        >>> normalize_ingredient_list([
        ...     " Water ",
        ...     "",
        ...     "Niacinamide",
        ...     "Panthenol.",
        ...     "   ",
        ...     "Glycerin,",
        ... ])
        ['water', 'niacinamide', 'panthenol', 'glycerin']
    """
    return [normalized for raw in ingredients if (normalized := normalize_ingredient_name(raw))]

