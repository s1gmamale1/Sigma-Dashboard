"""A deterministic mock source.

Used for any upstream that is not yet wired to real state, so the API and UI are
real on day one. Everything it emits is labeled ``source="mock"`` — the frontend
renders a visible MOCK badge so mocked data is never mistaken for live fleet
state (Built / Mocked / Spec-only discipline).
"""

from __future__ import annotations

from datetime import timedelta

from backend.app.hq.adapters.base import utcnow_naive
from backend.app.hq.models import (
    Blocker,
    Project,
    Session,
    Severity,
    Snapshot,
    Swarm,
    Task,
    TaskStatus,
    Worker,
    WorkerStatus,
    make_id,
)

NAME = "mock"


class MockAdapter:
    name = NAME

    def healthy(self) -> bool:
        return True

    def fetch_snapshot(self) -> Snapshot:
        now = utcnow_naive()

        def wid(s: str) -> str:
            return make_id(NAME, s)

        projects = [
            Project(
                id=wid("p-nets"),
                source=NAME,
                source_id="p-nets",
                name="NETS / Class A",
                slug="nets",
                owner="leo",
                status="active",
                updated_at=now,
            )
        ]
        workers = [
            Worker(
                id=wid("w-codex-1"),
                source=NAME,
                source_id="w-codex-1",
                name="codex-lane-1",
                kind="agent",
                model="codex",
                owner="leo",
                status=WorkerStatus.running,
                project_id=wid("p-nets"),
                session_id=wid("s-1"),
                task_id=wid("t-1"),
                worktree_path="/wt/mock-1",
                last_heartbeat=now,
            ),
            Worker(
                id=wid("w-gemini-1"),
                source=NAME,
                source_id="w-gemini-1",
                name="gemini-lane-1",
                kind="agent",
                model="gemini",
                owner="leo",
                status=WorkerStatus.blocked,
                project_id=wid("p-nets"),
                last_heartbeat=now - timedelta(seconds=900),
            ),
        ]
        sessions = [
            Session(
                id=wid("s-1"),
                source=NAME,
                source_id="s-1",
                worker_id=wid("w-codex-1"),
                project_id=wid("p-nets"),
                status="active",
                started_at=now - timedelta(minutes=20),
                last_activity=now,
            )
        ]
        swarms = [
            Swarm(
                id=wid("sw-1"),
                source=NAME,
                source_id="sw-1",
                name="nets-feature-swarm",
                topology="hierarchical",
                coordinator=wid("w-codex-1"),
                member_worker_ids=[wid("w-codex-1"), wid("w-gemini-1")],
                project_id=wid("p-nets"),
                status="active",
                last_heartbeat=now,
            )
        ]
        tasks = [
            Task(
                id=wid("t-1"),
                source=NAME,
                source_id="t-1",
                title="Wire HQ control plane",
                project_id=wid("p-nets"),
                assignee_worker_id=wid("w-codex-1"),
                status=TaskStatus.in_progress,
                priority=1,
                updated_at=now,
            )
        ]
        blockers = [
            Blocker(
                id=wid("b-1"),
                source=NAME,
                source_id="b-1",
                title="gemini-lane-1 lost heartbeat",
                severity=Severity.high,
                entity_type="worker",
                entity_id=wid("w-gemini-1"),
                owner="leo",
                status="open",
                opened_at=now - timedelta(minutes=10),
            )
        ]
        return Snapshot(
            source=NAME,
            healthy=True,
            fetched_at=now,
            projects=projects,
            workers=workers,
            sessions=sessions,
            swarms=swarms,
            tasks=tasks,
            blockers=blockers,
        )
