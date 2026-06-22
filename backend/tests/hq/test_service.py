from datetime import timedelta

from backend.app.hq.adapters.base import utcnow_naive
from backend.app.hq.adapters.mock import MockAdapter
from backend.app.hq.models import Snapshot, Worker, WorkerStatus
from backend.app.hq.service import HQService


class StaleSource:
    name = "sigmalink"

    def healthy(self) -> bool:
        return True

    def fetch_snapshot(self) -> Snapshot:
        old = utcnow_naive() - timedelta(seconds=600)
        return Snapshot(
            source="sigmalink",
            healthy=True,
            fetched_at=utcnow_naive(),
            workers=[
                Worker(
                    id="sigmalink:w1",
                    source="sigmalink",
                    source_id="w1",
                    name="W",
                    kind="agent",
                    status=WorkerStatus.running,
                    last_heartbeat=old,
                )
            ],
        )


class CountingSource:
    name = "mock"

    def __init__(self) -> None:
        self.calls = 0

    def healthy(self) -> bool:
        return True

    def fetch_snapshot(self) -> Snapshot:
        self.calls += 1
        return Snapshot(source="mock", healthy=True, fetched_at=utcnow_naive())


class BrokenSource:
    name = "sigmacontrol"

    def healthy(self) -> bool:
        return False

    def fetch_snapshot(self) -> Snapshot:
        raise RuntimeError("upstream exploded")


def test_merge_and_overview_counts() -> None:
    svc = HQService([MockAdapter(), StaleSource()])
    ov = svc.get_overview()
    assert ov.workers_total >= 3  # 2 from mock + 1 from stale source
    assert ov.sources["sigmalink"] is True
    assert ov.sources["mock"] is True


def test_stale_heartbeat_marked_unhealthy() -> None:
    svc = HQService([StaleSource()], stale_seconds=120)
    hbs = {h.entity_id: h for h in svc.get_snapshot()["heartbeats"]}
    assert "sigmalink:w1" in hbs
    assert hbs["sigmalink:w1"].healthy is False
    assert hbs["sigmalink:w1"].staleness_seconds is not None
    assert hbs["sigmalink:w1"].staleness_seconds >= 120


def test_cache_serves_within_ttl_and_force_refreshes() -> None:
    src = CountingSource()
    svc = HQService([src], ttl_seconds=60)
    svc.get_snapshot()
    svc.get_snapshot()
    assert src.calls == 1  # second call served from cache
    svc.get_snapshot(force=True)
    assert src.calls == 2  # forced refresh re-fetched


def test_one_broken_source_does_not_sink_the_page() -> None:
    svc = HQService([MockAdapter(), BrokenSource()])
    snap = svc.get_snapshot()
    assert len(snap["workers"]) >= 1  # mock still present
    assert snap["sources"]["sigmacontrol"] is False  # broken source flagged unhealthy
    assert snap["sources"]["mock"] is True
