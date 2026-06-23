"""Normalized control-plane entities.

Every entity carries ``source`` (which upstream it came from) and ``source_id``
(its id within that upstream); the aggregation service derives a globally stable
``id`` of the form ``"<source>:<source_id>"``. Datetimes are **naive UTC** to
match the rest of the dashboard (``[[naive-utc-timestamps]]``) — the frontend
renders them via ``parseServerDate``, never ``new Date``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel

# A source label. Kept as a plain ``str`` (not an Enum) so a future adapter can
# introduce a new source without a schema migration. Canonical values:
#   "sigmacontrol" | "sigmalink" | "mock" | "dashboard"
Source = str


class WorkerStatus(str, Enum):
    idle = "idle"
    running = "running"
    blocked = "blocked"
    offline = "offline"


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    review = "review"
    done = "done"
    blocked = "blocked"


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


def make_id(source: str, source_id: str) -> str:
    """Globally stable id for a normalized entity."""
    return f"{source}:{source_id}"


class Project(BaseModel):
    id: str
    source: Source
    source_id: str
    name: str
    slug: str
    owner: str | None = None
    status: str | None = None
    repo_path: str | None = None
    updated_at: datetime | None = None


class Worker(BaseModel):
    id: str
    source: Source
    source_id: str
    name: str
    kind: str  # "agent" | "human" | an agent-type string
    model: str | None = None
    owner: str | None = None
    status: WorkerStatus = WorkerStatus.offline
    project_id: str | None = None
    session_id: str | None = None
    task_id: str | None = None
    worktree_path: str | None = None
    last_heartbeat: datetime | None = None


class Session(BaseModel):
    id: str
    source: Source
    source_id: str
    worker_id: str | None = None
    project_id: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    last_activity: datetime | None = None
    transcript_ref: str | None = None


class Swarm(BaseModel):
    id: str
    source: Source
    source_id: str
    name: str
    topology: str | None = None
    coordinator: str | None = None
    member_worker_ids: list[str] = []
    project_id: str | None = None
    status: str | None = None
    last_heartbeat: datetime | None = None


class Task(BaseModel):
    id: str
    source: Source
    source_id: str
    title: str
    project_id: str | None = None
    assignee_worker_id: str | None = None
    status: TaskStatus = TaskStatus.todo
    priority: int | None = None
    blocker_ids: list[str] = []
    updated_at: datetime | None = None


class Blocker(BaseModel):
    id: str
    source: Source
    source_id: str
    title: str
    severity: Severity = Severity.medium
    entity_type: str | None = None  # "worker" | "task" | "session" | "project"
    entity_id: str | None = None
    owner: str | None = None
    status: str = "open"
    opened_at: datetime | None = None


class Heartbeat(BaseModel):
    entity_type: str  # "worker" | "session" | "swarm"
    entity_id: str
    source: Source
    ts: datetime | None = None
    staleness_seconds: int | None = None
    healthy: bool = False


class Snapshot(BaseModel):
    """Everything a single source knows at one point in time."""

    source: Source
    healthy: bool
    fetched_at: datetime
    projects: list[Project] = []
    workers: list[Worker] = []
    sessions: list[Session] = []
    swarms: list[Swarm] = []
    tasks: list[Task] = []
    blockers: list[Blocker] = []


class Overview(BaseModel):
    workers_total: int
    workers_running: int
    workers_blocked: int
    workers_offline: int
    sessions_active: int
    swarms_active: int
    tasks_open: int
    tasks_blocked: int
    blockers_open: int
    sources: dict[str, bool]  # source name -> healthy
    generated_at: datetime
