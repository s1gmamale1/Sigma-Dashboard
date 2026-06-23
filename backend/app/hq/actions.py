"""Signed, gated HQ control actions (read-first, write-behind-signoff).

Defence in depth, fail-closed at every layer:

1. ``require_edit`` auth (admin/manager).
2. action must be in the allowlist (``ACTIONS``) else 404.
3. ``SIGMA_HQ_ALLOW_ACTIONS`` must be on else 403.
4. ``SIGMA_HQ_ACTION_SECRET`` must be set else 403 (no secret ⇒ no control).
5. required target fields present else 422.
6. a valid ``X-Sigma-Signoff`` JWT bound to this action + target + a single-use
   nonce (operator-minted via scripts/hq_sign_action.py) else 403.
7. destructive actions additionally require ``SIGMA_HQ_ALLOW_DESTRUCTIVE`` else 403.
8. ``dry_run`` (default true) validates the whole gate and reports what *would*
   run — it never touches the socket. Execution forwards to the SigmaControl
   socket, whose own supervised-autonomy authz is a further backstop.

Every attempt (dry-run, executed, failed) is written to ``AuditLog``. Errors are
deterministic HTTP codes; there is no hidden best-effort write. The action
secret and control token never appear in responses, logs, or audit rows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app.auth import require_edit, require_view
from backend.app.config import Settings, get_settings
from backend.app.db import get_db, utc_now
from backend.app.hq.action_auth import (
    ActionAuthError,
    NonceCache,
    target_fingerprint,
    verify_signoff,
)
from backend.app.hq.adapters.control_creds import resolve_control_creds
from backend.app.hq.adapters.control_socket import ControlSocketError, make_control_socket_client
from backend.app.models import AuditLog
from backend.app.schemas import Envelope

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/hq/actions", tags=["HQ"])


@dataclass(frozen=True)
class ActionSpec:
    name: str
    tool: str  # SigmaControl socket tool to invoke
    required: tuple[str, ...]
    destructive: bool


# Narrow, safe-by-default allowlist. Destructive entries additionally require
# SIGMA_HQ_ALLOW_DESTRUCTIVE and are never fired during verification.
ACTIONS: dict[str, ActionSpec] = {
    "create_task": ActionSpec("create_task", "create_task", ("title",), False),
    "prompt_agent": ActionSpec("prompt_agent", "prompt_agent", ("sessionId", "prompt"), False),
    "send_keys": ActionSpec("send_keys", "send_keys", ("sessionId", "keys"), False),
    "read_pane": ActionSpec("read_pane", "read_pane", ("sessionId",), False),
    "stop_pane": ActionSpec("stop_pane", "stop_pane", ("sessionId",), True),
    "close_pane": ActionSpec("close_pane", "close_pane", ("sessionId",), True),
    "kill_swarm": ActionSpec("kill_swarm", "kill_swarm", ("swarmId",), True),
}


class ActionExecError(Exception):
    """Raised when forwarding an action to the SigmaControl socket fails."""


def execute_action(settings: Settings, spec: ActionSpec, target: dict[str, Any]) -> dict[str, Any]:
    """Forward a validated action to the live SigmaControl socket (read-first MVP
    only reaches here for non-destructive actions during normal operation)."""
    creds = resolve_control_creds(settings)
    if creds is None:
        raise ActionExecError("no SigmaControl credentials configured")
    try:
        with make_control_socket_client(creds.socket_path, creds.token, label=creds.label) as client:
            result = client.invoke(spec.tool, target)
    except (ControlSocketError, OSError) as exc:
        raise ActionExecError(f"socket {type(exc).__name__}") from None
    return {"ok": True, "result": result}


# --- injectable singletons (overridable in tests) ---------------------------

_NONCE_CACHE = NonceCache()


def get_nonce_cache() -> NonceCache:
    return _NONCE_CACHE


def get_action_executor() -> Callable[[Settings, ActionSpec, dict[str, Any]], dict[str, Any]]:
    return execute_action


def ok(data: object) -> Envelope:
    return Envelope(data=data, meta={}, error=None)


class ActionRequest(BaseModel):
    target: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True


def _audit(db, actor: str, action: str, target: dict[str, Any], detail: dict[str, Any]) -> None:
    resource = str(
        target.get("sessionId")
        or target.get("swarmId")
        or target.get("workspaceId")
        or target.get("title")
        or target_fingerprint(target)
    )[:120]
    db.add(
        AuditLog(
            actor=str(actor),
            action=f"hq.action.{action}",
            resource=resource,
            detail_json=json.dumps(detail),
            created_at=utc_now(),
        )
    )
    db.commit()


@router.get(
    "",
    response_model=Envelope,
    summary="HQ action capabilities + gate status",
)
def hq_actions_status(
    settings: Settings = Depends(get_settings),
    _: object = Depends(require_view),
) -> Envelope:
    """Read-only: what actions exist and whether the gate is open. No secrets."""
    return ok(
        {
            "enabled": settings.hq_allow_actions,
            "destructive_enabled": settings.hq_allow_destructive,
            "signoff_required": True,
            "signoff_configured": bool(settings.hq_action_secret),
            "actions": [
                {"name": s.name, "tool": s.tool, "required": list(s.required), "destructive": s.destructive}
                for s in ACTIONS.values()
            ],
        }
    )


@router.post(
    "/{action}",
    response_model=Envelope,
    summary="Submit a signed HQ control action (dry-run by default)",
    responses={
        403: {"description": "Disabled, no secret, missing/invalid signoff, or destructive-not-allowed."},
        404: {"description": "Unknown action."},
        422: {"description": "Missing required target fields."},
        502: {"description": "Action forwarded but the control socket failed."},
    },
)
def hq_action(
    action: str,
    body: ActionRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    db=Depends(get_db),
    nonce_cache: NonceCache = Depends(get_nonce_cache),
    executor: Callable = Depends(get_action_executor),
    actor: object = Depends(require_edit),
) -> Envelope:
    spec = ACTIONS.get(action)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown action {action!r}")
    if not settings.hq_allow_actions:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HQ control actions are disabled (SIGMA_HQ_ALLOW_ACTIONS).")
    if not settings.hq_action_secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "HQ action signing secret is not configured.")

    target = body.target or {}
    missing = [k for k in spec.required if not target.get(k)]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"missing required target field(s): {missing}")

    signoff = request.headers.get("X-Sigma-Signoff", "")
    try:
        claims = verify_signoff(settings.hq_action_secret, signoff, action, target, nonce_cache=nonce_cache)
    except ActionAuthError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"signoff rejected: {exc}")

    if spec.destructive and not settings.hq_allow_destructive:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "destructive HQ actions are disabled (SIGMA_HQ_ALLOW_DESTRUCTIVE)."
        )

    nonce = claims.get("nonce")
    if body.dry_run:
        _audit(db, str(actor), action, target, {"dry_run": True, "destructive": spec.destructive, "outcome": "validated", "nonce": nonce})
        return ok(
            {
                "action": action,
                "dry_run": True,
                "destructive": spec.destructive,
                "target_fingerprint": target_fingerprint(target),
                "would_invoke": spec.tool,
                "status": "validated",
            }
        )

    try:
        result = executor(settings, spec, target)
    except ActionExecError as exc:
        _audit(db, str(actor), action, target, {"dry_run": False, "destructive": spec.destructive, "outcome": "failed", "error": str(exc), "nonce": nonce})
        logger.warning("hq action %s execution failed: %s", action, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"action execution failed: {exc}")

    _audit(db, str(actor), action, target, {"dry_run": False, "destructive": spec.destructive, "outcome": "executed", "nonce": nonce})
    logger.info("hq action %s executed by %s on %s", action, actor, _audit_target(target))
    return ok({"action": action, "dry_run": False, "destructive": spec.destructive, "status": "executed", "result": result})


def _audit_target(target: dict[str, Any]) -> str:
    return str(target.get("sessionId") or target.get("swarmId") or target.get("workspaceId") or "—")
