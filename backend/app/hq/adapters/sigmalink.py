"""Read-only SigmaLink source.

SigmaLink is the Electron multi-agent dev environment — a Command Room of agent
panes, each a git worktree/lane. This adapter reads a JSON state file (path from
``SIGMA_HQ_SIGMALINK_STATE``) and maps lanes→workers, panes/sessions→sessions,
and swarms→swarms.

The field names below are the *contract* this adapter expects. If SigmaLink does
not yet publish such a file, the adapter degrades to unhealthy/empty and the mock
source covers SigmaLink in the UI (visibly labeled) until the real source path +
schema are confirmed — see plan Blocker #1.
"""

from __future__ import annotations

from typing import Any

from backend.app.hq.adapters.base import (
    load_json_state,
    parse_dt,
    scrub,
    utcnow_naive,
)
from backend.app.hq.models import (
    Session,
    Snapshot,
    Swarm,
    Worker,
    WorkerStatus,
    make_id,
)

NAME = "sigmalink"


def _first(rec: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return None


def _worker_status(value: Any) -> WorkerStatus:
    try:
        return WorkerStatus(str(value).lower())
    except ValueError:
        return WorkerStatus.offline


def _gid(source_id: Any) -> str:
    return make_id(NAME, str(source_id))


class SigmaLinkAdapter:
    name = NAME

    def __init__(self, state_path: str | None) -> None:
        self._state_path = state_path

    def _load(self) -> dict[str, Any] | None:
        return load_json_state(self._state_path)

    def healthy(self) -> bool:
        return self._load() is not None

    def fetch_snapshot(self) -> Snapshot:
        now = utcnow_naive()
        data = self._load()
        if data is None:
            return Snapshot(source=NAME, healthy=False, fetched_at=now)

        workers: list[Worker] = []
        for raw in data.get("lanes", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "lane_id", "name")
            if sid is None:
                continue
            workers.append(
                Worker(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    name=str(_first(rec, "name", "id") or sid),
                    kind=str(_first(rec, "kind") or "agent"),
                    model=_opt_str(_first(rec, "model", "cli")),
                    owner=_opt_str(_first(rec, "owner")),
                    status=_worker_status(_first(rec, "status")),
                    project_id=_opt_gid(_first(rec, "project_id", "project")),
                    session_id=_opt_gid(_first(rec, "session_id", "session")),
                    task_id=_opt_gid(_first(rec, "task_id", "task")),
                    worktree_path=_opt_str(_first(rec, "worktree_path", "worktree", "path")),
                    last_heartbeat=parse_dt(
                        _first(rec, "last_heartbeat", "last_activity", "heartbeat", "updated_at")
                    ),
                )
            )

        sessions: list[Session] = []
        for raw in data.get("sessions", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "session_id")
            if sid is None:
                continue
            sessions.append(
                Session(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    worker_id=_opt_gid(_first(rec, "worker_id", "lane_id", "lane")),
                    project_id=_opt_gid(_first(rec, "project_id", "project")),
                    status=_opt_str(_first(rec, "status")),
                    started_at=parse_dt(_first(rec, "started_at", "created_at")),
                    last_activity=parse_dt(_first(rec, "last_activity", "updated_at")),
                    transcript_ref=_opt_str(_first(rec, "transcript_ref", "transcript")),
                )
            )

        swarms: list[Swarm] = []
        for raw in data.get("swarms", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "swarm_id", "name")
            if sid is None:
                continue
            members = _first(rec, "member_worker_ids", "members") or []
            swarms.append(
                Swarm(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    name=str(_first(rec, "name", "id") or sid),
                    topology=_opt_str(_first(rec, "topology")),
                    coordinator=_opt_gid(_first(rec, "coordinator")),
                    member_worker_ids=[_gid(m) for m in members if m is not None],
                    project_id=_opt_gid(_first(rec, "project_id", "project")),
                    status=_opt_str(_first(rec, "status")),
                    last_heartbeat=parse_dt(_first(rec, "last_heartbeat", "updated_at")),
                )
            )

        return Snapshot(
            source=NAME,
            healthy=True,
            fetched_at=now,
            workers=workers,
            sessions=sessions,
            swarms=swarms,
        )


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_gid(value: Any) -> str | None:
    return None if value is None else _gid(value)
