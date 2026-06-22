"""Control-action stub — scaffolded but DISABLED (read-first, write-later).

This is the future home of fleet control (stop a worker, assign a task, kill a
session). In the MVP nothing is wired:

* ``SIGMA_HQ_ALLOW_ACTIONS`` defaults to false → every action returns **403**.
* Even when enabled, an action requires an explicit ``X-Sigma-Signoff`` header
  (the sign-off gate) and still returns **501 Not Implemented** — no upstream
  state is ever mutated.

No code path in this module performs a write. It exists so the contract and gate
are visible and tested now, before any real control is added.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.auth import require_edit
from backend.app.config import Settings, get_settings

router = APIRouter(prefix="/api/v1/hq/actions", tags=["HQ"])


@router.post(
    "/{action}",
    summary="Control action (disabled in MVP)",
    responses={
        403: {"description": "Actions disabled, or sign-off header missing."},
        501: {"description": "Action recognized but not implemented (read-only MVP)."},
    },
)
def hq_action(
    action: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    _: object = Depends(require_edit),
) -> None:
    """Always refuses in the MVP. Order: feature-flag gate → sign-off gate → 501."""
    if not settings.hq_allow_actions:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "HQ control actions are disabled (read-only mode). "
            "Set SIGMA_HQ_ALLOW_ACTIONS=1 to enable.",
        )
    if not request.headers.get("X-Sigma-Signoff"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "HQ control actions require an explicit X-Sigma-Signoff header.",
        )
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"HQ control action {action!r} is not implemented in the MVP (read-only).",
    )
