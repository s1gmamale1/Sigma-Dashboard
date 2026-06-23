"""Signed action-approval tokens for HQ control actions.

A signoff (the ``X-Sigma-Signoff`` header) is a short-lived HS256 JWT, minted
out-of-band by an operator who holds ``SIGMA_HQ_ACTION_SECRET`` (see
``scripts/hq_sign_action.py``). It is bound to a single action + a fingerprint
of the exact target args + a single-use nonce, so the dashboard cannot
self-authorize and a captured token cannot be replayed or retargeted.

The secret is never logged or returned. An unset secret makes signing AND
verification impossible (fail-closed) — control can never be silently open.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from jose import JWTError, jwt

ALGORITHM = "HS256"
ACTION_SCOPE = "hq.action"
DEFAULT_TTL_SECONDS = 120


class ActionAuthError(Exception):
    """Signoff missing/invalid/expired/replayed. Carries a safe reason, never the token."""


def target_fingerprint(target: dict[str, Any] | None) -> str:
    """Stable, order-independent fingerprint of the target args."""
    canonical = json.dumps(target or {}, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mint_signoff(
    secret: str,
    action: str,
    target: dict[str, Any] | None,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    nonce: str | None = None,
    now: int | None = None,
) -> str:
    if not secret:
        raise ActionAuthError("no action secret configured — cannot sign")
    issued = int(now if now is not None else time.time())
    if nonce is None:
        nonce = hashlib.sha256(f"{action}:{issued}:{target_fingerprint(target)}".encode()).hexdigest()[:24]
    claims = {
        "scope": ACTION_SCOPE,
        "act": action,
        "tgt": target_fingerprint(target),
        "nonce": nonce,
        "iat": issued,
        "exp": issued + ttl_seconds,
    }
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


class NonceCache:
    """In-process single-use nonce store (anti-replay within the JWT TTL window).

    Single-uvicorn-process scope — adequate for the launchd dashboard. Entries
    self-expire at their token ``exp``.
    """

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def _prune(self, now: int) -> None:
        for n, exp in list(self._seen.items()):
            if exp <= now:
                del self._seen[n]

    def check_and_add(self, nonce: str, exp: int, now: int) -> bool:
        self._prune(now)
        if nonce in self._seen:
            return False
        self._seen[nonce] = exp
        return True


def verify_signoff(
    secret: str,
    token: str,
    action: str,
    target: dict[str, Any] | None,
    *,
    now: int | None = None,
    nonce_cache: NonceCache,
) -> dict[str, Any]:
    if not secret:
        raise ActionAuthError("no action secret configured — control disabled")
    if not token:
        raise ActionAuthError("missing signoff token")
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except JWTError as exc:
        msg = str(exc).lower()
        if "expire" in msg:
            raise ActionAuthError("signoff expired") from None
        raise ActionAuthError("invalid signoff signature/format") from None

    if claims.get("scope") != ACTION_SCOPE:
        raise ActionAuthError("signoff wrong scope")
    if claims.get("act") != action:
        raise ActionAuthError("signoff action mismatch")
    if claims.get("tgt") != target_fingerprint(target):
        raise ActionAuthError("signoff target mismatch")
    nonce = claims.get("nonce")
    if not nonce:
        raise ActionAuthError("signoff missing nonce")
    current = int(now if now is not None else time.time())
    if not nonce_cache.check_and_add(str(nonce), int(claims.get("exp", current)), current):
        raise ActionAuthError("signoff nonce already used (replay)")
    return claims
