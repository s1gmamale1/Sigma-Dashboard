"""Adapter contract + shared helpers.

Every source implements :class:`ControlPlaneSource`. Sources are **read-only** —
they open files for reading and never mutate upstream state. Every raw record a
source ingests MUST be passed through :func:`scrub` before any of its values flow
into a normalized entity, so tokens/keys/secrets can never leave the process.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from backend.app.hq.models import Snapshot

# Keys whose name looks like it carries a credential. Matched case-insensitively
# anywhere in the key. ``env`` is included because upstream state files sometimes
# inline a whole process environment, which is the classic secret-leak vector.
SECRET_KEY_RE = re.compile(
    r"(token|secret|password|passwd|api[_-]?key|apikey|authorization|auth_header|cookie|credential|private[_-]?key|\.env|^env$)",
    re.IGNORECASE,
)


def scrub(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``record`` with secret-shaped keys removed.

    Non-mutating: the caller's dict is left untouched. Only the top level is
    filtered; adapters must not promote nested untrusted blobs (e.g. a raw
    ``env`` dict) into entity fields.
    """
    return {k: v for k, v in record.items() if not SECRET_KEY_RE.search(str(k))}


def utcnow_naive() -> datetime:
    """Naive-UTC 'now', matching the dashboard's timestamp convention."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_dt(value: Any) -> datetime | None:
    """Best-effort parse of an upstream timestamp into a naive datetime.

    Accepts ISO-8601 strings (with or without a trailing ``Z``/offset) and epoch
    seconds. Returns ``None`` for anything unparseable so one bad field can never
    sink a whole snapshot.
    """
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        raw = raw.replace("Z", "").replace("z", "")
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


@runtime_checkable
class ControlPlaneSource(Protocol):
    """A read-only upstream the HQ service can pull a snapshot from."""

    name: str

    def fetch_snapshot(self) -> Snapshot:
        """Return everything this source currently knows."""
        ...

    def healthy(self) -> bool:
        """Whether the source is reachable/parseable right now."""
        ...
