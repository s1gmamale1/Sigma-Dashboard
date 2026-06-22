"""Read-only SigmaControl source.

SigmaControl is the control/ownership layer; this adapter reads its JSON state
file (path from ``SIGMA_HQ_SIGMACONTROL_STATE``) and maps the planning domain it
owns: projects, tasks, and blockers (execution entities — workers/sessions/
swarms — come from SigmaLink, so there is no mapping overlap between the two).

Missing/unreadable/malformed state degrades to unhealthy/empty; the mock source
then covers SigmaControl in the UI (visibly labeled) until the real source path +
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
    Blocker,
    Project,
    Severity,
    Snapshot,
    Task,
    TaskStatus,
    make_id,
)

NAME = "sigmacontrol"


def _first(rec: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in rec and rec[k] is not None:
            return rec[k]
    return None


def _gid(source_id: Any) -> str:
    return make_id(NAME, str(source_id))


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_gid(value: Any) -> str | None:
    return None if value is None else _gid(value)


def _task_status(value: Any) -> TaskStatus:
    try:
        return TaskStatus(str(value).lower())
    except ValueError:
        return TaskStatus.todo


def _severity(value: Any) -> Severity:
    try:
        return Severity(str(value).lower())
    except ValueError:
        return Severity.medium


class SigmaControlAdapter:
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

        projects: list[Project] = []
        for raw in data.get("projects", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "slug", "name")
            if sid is None:
                continue
            projects.append(
                Project(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    name=str(_first(rec, "name", "id") or sid),
                    slug=str(_first(rec, "slug", "id") or sid),
                    owner=_opt_str(_first(rec, "owner")),
                    status=_opt_str(_first(rec, "status")),
                    repo_path=_opt_str(_first(rec, "repo_path", "path")),
                    updated_at=parse_dt(_first(rec, "updated_at", "modified_at")),
                )
            )

        tasks: list[Task] = []
        for raw in data.get("tasks", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "task_id")
            if sid is None:
                continue
            blocker_ids = _first(rec, "blocker_ids", "blockers") or []
            tasks.append(
                Task(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    title=str(_first(rec, "title", "name") or sid),
                    project_id=_opt_gid(_first(rec, "project_id", "project")),
                    assignee_worker_id=_opt_gid(_first(rec, "assignee_worker_id", "assignee")),
                    status=_task_status(_first(rec, "status")),
                    priority=_opt_int(_first(rec, "priority")),
                    blocker_ids=[_gid(b) for b in blocker_ids if b is not None],
                    updated_at=parse_dt(_first(rec, "updated_at", "modified_at")),
                )
            )

        blockers: list[Blocker] = []
        for raw in data.get("blockers", []) or []:
            if not isinstance(raw, dict):
                continue
            rec = scrub(raw)
            sid = _first(rec, "id", "blocker_id")
            if sid is None:
                continue
            blockers.append(
                Blocker(
                    id=_gid(sid),
                    source=NAME,
                    source_id=str(sid),
                    title=str(_first(rec, "title", "name") or sid),
                    severity=_severity(_first(rec, "severity")),
                    entity_type=_opt_str(_first(rec, "entity_type")),
                    entity_id=_opt_gid(_first(rec, "entity_id", "entity")),
                    owner=_opt_str(_first(rec, "owner")),
                    status=str(_first(rec, "status") or "open"),
                    opened_at=parse_dt(_first(rec, "opened_at", "created_at")),
                )
            )

        return Snapshot(
            source=NAME,
            healthy=True,
            fetched_at=now,
            projects=projects,
            tasks=tasks,
            blockers=blockers,
        )


def _opt_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None
