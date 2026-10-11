"""
Centralised domain exception hierarchy.

All service-layer business exceptions should inherit from
:class:`DomainError` so that the global exception handlers registered
in :mod:`main` can translate them into consistent HTTP responses
without leaking internal details.

Usage in a service::

    from app.core.exceptions import DomainError

    class IngredientNotFoundError(DomainError):
        status_code = 404

        def __init__(self, detail: str) -> None:
            super().__init__(detail)

Usage in a route handler (no try/except needed)::

    @router.get("/ingredients/{id}")
    async def get_ingredient(id: str, service = Depends(...)):
        ingredient = await service.get_ingredient_by_id(id)
        return ingredient  # DomainError raised in service is handled globally
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain / business-logic errors.

    Subclasses **must** set ``status_code`` to the appropriate HTTP
    status code.  The ``detail`` attribute carries a user-safe message
    that will be included in the JSON response body.
    """

    status_code: int = 500
    detail: str = "An unexpected error occurred"

    def __init__(self, detail: str | None = None) -> None:
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)
