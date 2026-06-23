"""Aggregation service.

Pulls a :class:`Snapshot` from every registered source, merges them into one
fleet view, computes heartbeat staleness server-side (naive-UTC), and TTL-caches
the result behind a refresh lock so a burst of requests triggers at most one
upstream fetch per TTL window (the ``_import_lock`` serialization pattern used by
attendance imports). One misbehaving source can never sink the page — its fetch
is guarded and it is simply reported unhealthy.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from backend.app.hq.adapters.base import ControlPlaneSource, utcnow_naive
from backend.app.hq.models import (
    Blocker,
    Heartbeat,
    Overview,
    Project,
    Session,
    Swarm,
    Task,
    TaskStatus,
    Worker,
    WorkerStatus,
)

logger = logging.getLogger("uvicorn.error")

_ACTIVE_SESSION = {"active", "running", "open"}
_ACTIVE_SWARM = {"active", "running"}


class HQService:
    def __init__(
        self,
        sources: list[ControlPlaneSource],
        ttl_seconds: int = 5,
        stale_seconds: int = 120,
    ) -> None:
        self._sources = sources
        self._ttl = max(0, ttl_seconds)
        self._stale = max(1, stale_seconds)
        self._lock = threading.Lock()
        self._cache: dict[str, Any] | None = None
        self._cache_at = None  # naive-UTC datetime of last refresh

    # ---- public API -----------------------------------------------------

    def get_snapshot(self, force: bool = False) -> dict[str, Any]:
        now = utcnow_naive()
        if not force and self._fresh(now):
            return self._cache  # type: ignore[return-value]
        with self._lock:
            # Double-check: another thread may have refreshed while we waited.
            if not force and self._fresh(utcnow_naive()):
                return self._cache  # type: ignore[return-value]
            self._cache = self._rebuild()
            self._cache_at = utcnow_naive()
            return self._cache

    def get_overview(self, force: bool = False) -> Overview:
        snap = self.get_snapshot(force=force)
        workers: list[Worker] = snap["workers"]
        tasks: list[Task] = snap["tasks"]
        return Overview(
            workers_total=len(workers),
            workers_running=sum(1 for w in workers if w.status == WorkerStatus.running),
            workers_blocked=sum(1 for w in workers if w.status == WorkerStatus.blocked),
            workers_offline=sum(1 for w in workers if w.status == WorkerStatus.offline),
            sessions_active=sum(
                1 for s in snap["sessions"] if (s.status or "").lower() in _ACTIVE_SESSION
            ),
            swarms_active=sum(
                1 for sw in snap["swarms"] if (sw.status or "").lower() in _ACTIVE_SWARM
            ),
            tasks_open=sum(1 for t in tasks if t.status != TaskStatus.done),
            tasks_blocked=sum(1 for t in tasks if t.status == TaskStatus.blocked),
            blockers_open=sum(1 for b in snap["blockers"] if (b.status or "").lower() == "open"),
            sources=snap["sources"],
            generated_at=snap["generated_at"],
        )

    # ---- internals ------------------------------------------------------

    def _fresh(self, now) -> bool:
        if self._cache is None or self._cache_at is None:
            return False
        return (now - self._cache_at).total_seconds() < self._ttl

    def _rebuild(self) -> dict[str, Any]:
        now = utcnow_naive()
        projects: list[Project] = []
        workers: list[Worker] = []
        sessions: list[Session] = []
        swarms: list[Swarm] = []
        tasks: list[Task] = []
        blockers: list[Blocker] = []
        sources: dict[str, bool] = {}

        for src in self._sources:
            try:
                snap = src.fetch_snapshot()
            except Exception:  # noqa: BLE001 — one bad source must not sink the page
                logger.exception("hq: source %r failed to fetch", getattr(src, "name", "?"))
                sources[getattr(src, "name", "unknown")] = False
                continue
            sources[snap.source] = snap.healthy
            projects.extend(snap.projects)
            workers.extend(snap.workers)
            sessions.extend(snap.sessions)
            swarms.extend(snap.swarms)
            tasks.extend(snap.tasks)
            blockers.extend(snap.blockers)

        heartbeats = self._heartbeats(workers, sessions, swarms, now)

        return {
            "projects": projects,
            "workers": workers,
            "sessions": sessions,
            "swarms": swarms,
            "tasks": tasks,
            "blockers": blockers,
            "heartbeats": heartbeats,
            "sources": sources,
            "generated_at": now,
        }

    def _heartbeats(
        self,
        workers: list[Worker],
        sessions: list[Session],
        swarms: list[Swarm],
        now,
    ) -> list[Heartbeat]:
        out: list[Heartbeat] = []

        def add(entity_type: str, entity_id: str, source: str, ts) -> None:
            staleness = int((now - ts).total_seconds()) if ts is not None else None
            healthy = staleness is not None and staleness <= self._stale
            out.append(
                Heartbeat(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    source=source,
                    ts=ts,
                    staleness_seconds=staleness,
                    healthy=healthy,
                )
            )

        for w in workers:
            add("worker", w.id, w.source, w.last_heartbeat)
        for s in sessions:
            add("session", s.id, s.source, s.last_activity)
        for sw in swarms:
            add("swarm", sw.id, sw.source, sw.last_heartbeat)
        return out
