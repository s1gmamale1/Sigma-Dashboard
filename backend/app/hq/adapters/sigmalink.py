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

from datetime import datetime
from typing import Any

from backend.app.hq.adapters.base import (
    load_json_state,
    parse_dt,
    scrub,
    utcnow_naive,
)
from backend.app.hq.adapters.control_socket import ControlSocketError, make_control_socket_client
from backend.app.hq.models import (
    Blocker,
    Project,
    Session,
    Severity,
    Snapshot,
    Swarm,
    Worker,
    WorkerStatus,
    make_id,
)

# SigmaLink notification-center severities that count as actionable HQ blockers.
# "info" (e.g. clean pane exits) is intentionally excluded.
_ALERT_SEVERITY = {
    "critical": Severity.critical,
    "error": Severity.high,
    "warning": Severity.medium,
    "warn": Severity.medium,
}

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

    def __init__(
        self,
        state_path: str | None,
        *,
        socket_path: str | None = None,
        token: str | None = None,
        label: str = "sigma-hq",
    ) -> None:
        self._state_path = state_path
        self._socket_path = socket_path
        self._token = token
        self._label = label

    def _load(self) -> dict[str, Any] | None:
        return load_json_state(self._state_path)

    def _load_live(self) -> dict[str, Any] | None:
        if not self._socket_path or not self._token:
            return None
        try:
            with make_control_socket_client(
                self._socket_path,
                self._token,
                label=self._label,
            ) as client:
                workspaces = client.invoke("list_workspaces").get("workspaces", [])
                sessions = client.invoke("list_active_sessions").get("sessions", [])
                # Blockers/alerts are best-effort: a get_app_state failure must not
                # sink the (already-fetched) workers/sessions/projects.
                notifications: list[Any] = []
                try:
                    app_state = client.invoke("get_app_state") or {}
                    state = app_state.get("state") or {}
                    notifications = (state.get("notifications") or {}).get("recent") or []
                except Exception:  # noqa: BLE001 — blockers degrade quietly
                    notifications = []
        except (ControlSocketError, OSError):
            return None
        return {"workspaces": workspaces, "sessions": sessions, "notifications": notifications}

    def healthy(self) -> bool:
        return self._load() is not None or self._load_live() is not None

    def fetch_snapshot(self) -> Snapshot:
        now = utcnow_naive()
        data = self._load()
        if data is None:
            data = self._load_live()
        if data is None:
            return Snapshot(source=NAME, healthy=False, fetched_at=now)

        return _snapshot_from_state(data, now)


def _snapshot_from_state(data: dict[str, Any], now) -> Snapshot:
    projects: list[Project] = []
    for raw in data.get("workspaces", []) or []:
        if not isinstance(raw, dict):
            continue
        rec = scrub(raw)
        sid = _first(rec, "id", "workspaceId", "rootPath", "name")
        if sid is None:
            continue
        active = bool(_first(rec, "active"))
        projects.append(
            Project(
                id=_gid(sid),
                source=NAME,
                source_id=str(sid),
                name=str(_first(rec, "name", "id") or sid),
                slug=str(_first(rec, "name", "id") or sid),
                status="active" if active else "open",
                repo_path=_opt_str(_first(rec, "rootPath", "repo_path", "path")),
                updated_at=now,
            )
        )

    workers: list[Worker] = []
    sessions: list[Session] = []
    worker_ids_by_swarm: dict[str, list[str]] = {}

    # Live External Control reports panes as sessions. Treat every pane as a
    # session; agent panes also become workers. Shell panes are preserved only as
    # sessions so the UI does not inflate the agent roster with terminals.
    for raw in data.get("sessions", []) or []:
        if not isinstance(raw, dict):
            continue
        rec = scrub(raw)
        sid = _first(rec, "sessionId", "id", "session_id")
        if sid is None:
            continue
        provider = _opt_str(_first(rec, "provider", "model", "cli"))
        status = _opt_str(_first(rec, "status")) or "running"
        worker_source_id = _first(rec, "agentKey", "worker_id", "lane_id", "lane") or sid
        worker_id = _gid(worker_source_id)
        is_agent = provider != "shell"
        if is_agent:
            workers.append(
                Worker(
                    id=worker_id,
                    source=NAME,
                    source_id=str(worker_source_id),
                    name=str(_first(rec, "name", "agentKey", "sessionId") or worker_source_id),
                    kind="agent",
                    model=provider,
                    status=_worker_status(status),
                    session_id=_gid(sid),
                    last_heartbeat=now,
                )
            )
        sessions.append(
            Session(
                id=_gid(sid),
                source=NAME,
                source_id=str(sid),
                worker_id=worker_id if is_agent else None,
                status=status,
                started_at=parse_dt(_first(rec, "started_at", "created_at")),
                last_activity=parse_dt(_first(rec, "last_activity", "updated_at")) or now,
                transcript_ref=str(sid),
            )
        )
        swarm_id = _first(rec, "swarmId", "swarm_id")
        if swarm_id is not None and is_agent:
            worker_ids_by_swarm.setdefault(str(swarm_id), []).append(worker_id)

    # Legacy/file-state lanes remain supported for the pre-existing JSON adapter
    # contract. Avoid duplicating live workers already created from sessions.
    seen_workers = {w.id for w in workers}
    for raw in data.get("lanes", []) or []:
        if not isinstance(raw, dict):
            continue
        rec = scrub(raw)
        sid = _first(rec, "id", "lane_id", "name")
        if sid is None:
            continue
        wid = _gid(sid)
        if wid in seen_workers:
            continue
        workers.append(
            Worker(
                id=wid,
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

    swarms: list[Swarm] = []
    seen_swarms: set[str] = set()
    for sid, members in worker_ids_by_swarm.items():
        swarms.append(
            Swarm(
                id=_gid(sid),
                source=NAME,
                source_id=sid,
                name=sid,
                member_worker_ids=members,
                status="running",
                last_heartbeat=now,
            )
        )
        seen_swarms.add(_gid(sid))

    for raw in data.get("swarms", []) or []:
        if not isinstance(raw, dict):
            continue
        rec = scrub(raw)
        sid = _first(rec, "id", "swarm_id", "name")
        if sid is None:
            continue
        gid = _gid(sid)
        if gid in seen_swarms:
            continue
        members = _first(rec, "member_worker_ids", "members") or []
        swarms.append(
            Swarm(
                id=gid,
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

    blockers = _notifications_to_blockers(data.get("notifications") or [], now)

    return Snapshot(
        source=NAME,
        healthy=True,
        fetched_at=now,
        projects=projects,
        workers=workers,
        sessions=sessions,
        swarms=swarms,
        blockers=blockers,
    )


def _ms_to_dt(value: Any) -> datetime | None:
    """SigmaLink timestamps are epoch milliseconds; tolerate seconds too."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1e12:  # milliseconds
        v = v / 1000.0
    try:
        return datetime.utcfromtimestamp(v)
    except (OverflowError, OSError, ValueError):
        return None


def _notifications_to_blockers(notifs: list[Any], now: datetime) -> list[Blocker]:
    """Map actionable notification-center entries to HQ blockers/alerts.

    Real live data from ``get_app_state.state.notifications.recent`` — only
    error/warning/critical severities become blockers; info is dropped.
    """
    out: list[Blocker] = []
    for raw in notifs:
        if not isinstance(raw, dict):
            continue
        sev = _ALERT_SEVERITY.get(str(raw.get("severity", "")).lower())
        if sev is None:
            continue
        rec = scrub(raw)
        nid = rec.get("id") or rec.get("createdAt")
        if nid is None:
            continue
        out.append(
            Blocker(
                id=_gid(nid),
                source=NAME,
                source_id=str(nid),
                title=str(_first(rec, "title", "kind") or "alert"),
                severity=sev,
                entity_type="alert",
                entity_id=_opt_gid(_first(rec, "workspaceId")),
                status="open" if rec.get("readAt") in (None, "", 0) else "resolved",
                opened_at=_ms_to_dt(rec.get("createdAt")),
            )
        )
    return out


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_gid(value: Any) -> str | None:
    return None if value is None else _gid(value)
