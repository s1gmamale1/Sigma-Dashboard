from datetime import datetime

from backend.app.hq.models import (
    Overview,
    Snapshot,
    Worker,
    WorkerStatus,
    make_id,
)


def test_make_id_is_stable() -> None:
    assert make_id("sigmalink", "lane-3") == "sigmalink:lane-3"


def test_worker_defaults_offline() -> None:
    w = Worker(id="x", source="mock", source_id="x", name="A", kind="agent")
    assert w.status == WorkerStatus.offline


def test_empty_snapshot_round_trips() -> None:
    snap = Snapshot(source="mock", healthy=True, fetched_at=datetime(2026, 6, 23, 10, 0, 0))
    assert snap.workers == [] and snap.tasks == [] and snap.blockers == []


def test_overview_requires_counts() -> None:
    ov = Overview(
        workers_total=0,
        workers_running=0,
        workers_blocked=0,
        workers_offline=0,
        sessions_active=0,
        swarms_active=0,
        tasks_open=0,
        tasks_blocked=0,
        blockers_open=0,
        sources={"mock": True},
        generated_at=datetime(2026, 6, 23, 10, 0, 0),
    )
    assert ov.sources["mock"] is True
