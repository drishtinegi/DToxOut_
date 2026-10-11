"""
Admin audit trail logging.

Provides :func:`audit_log` to record security-sensitive admin operations
(create, update, delete) to the application log.  Each audit entry
contains:

- ``audit=True`` — marker so audit lines can be filtered
- ``action`` — human-readable action name (``create_ingredient``, etc.)
- ``admin_id`` — UUID of the admin user performing the action
- ``target_id`` — UUID of the affected resource (if any)
- ``status`` — ``success`` or ``failure``
- ``request_id`` — correlation ID from the request logging middleware

Audit events are logged at **INFO** level through the standard logging
pipeline.  The centralized :class:`~app.core.logging.SensitiveFilter`
scrubs passwords and tokens before they reach any handler.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("app.audit")


def audit_log(
    *,
    action: str,
    admin_id: str,
    target_id: Optional[str] = None,
    status: str = "success",
    request_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> None:
    """Emit a single audit log line.

    All parameters are keyword-only to prevent accidental positional usage.

    Args:
        action: Short action name, e.g. ``create_ingredient``,
            ``delete_ingredient``.
        admin_id: UUID of the admin user performing the action.
        target_id: UUID of the affected resource.  ``None`` for
            actions that don't target a specific resource.
        status: ``"success"`` or ``"failure"``.
        request_id: Correlation ID from the request logging middleware.
            Passed via ``extra`` so the formatter can render it.
        detail: Optional free-text detail (kept short, no secrets).
    """
    # Build a single pre-formatted string (no %s args) so that the
    # SensitiveFilter's regex matching operates on the final message,
    # not on a format template.
    parts = [f"action={action} admin_id={admin_id} status={status}"]
    if target_id is not None:
        parts.append(f"target_id={target_id}")
    if detail:
        parts.append(f"detail={detail}")
    logger.info(
        " ".join(parts),
        extra={
            "request_id": request_id or "",
            "audit": True,
        },
    )
