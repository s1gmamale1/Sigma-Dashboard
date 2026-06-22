import json

from backend.app.hq.models import WorkerStatus
from backend.app.hq.adapters.sigmalink import SigmaLinkAdapter


def test_missing_state_is_unhealthy_and_empty(tmp_path) -> None:
    a = SigmaLinkAdapter(str(tmp_path / "nope.json"))
    assert a.healthy() is False
    snap = a.fetch_snapshot()
    assert snap.healthy is False
    assert snap.source == "sigmalink"
    assert snap.workers == []


def test_unset_path_is_unhealthy() -> None:
    a = SigmaLinkAdapter(None)
    assert a.healthy() is False
    assert a.fetch_snapshot().workers == []


def test_lanes_map_to_workers_and_scrub_secrets(tmp_path) -> None:
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "lanes": [
                    {
                        "id": "lane-1",
                        "name": "codex-A",
                        "model": "codex",
                        "status": "running",
                        "worktree": "/wt/a",
                        "owner": "leo",
                        "last_activity": "2026-06-23T10:00:00",
                        "api_token": "LEAKED-SECRET",
                    }
                ]
            }
        )
    )
    snap = SigmaLinkAdapter(str(p)).fetch_snapshot()
    assert snap.healthy is True
    assert len(snap.workers) == 1
    w = snap.workers[0]
    assert w.source == "sigmalink"
    assert w.id == "sigmalink:lane-1"
    assert w.name == "codex-A"
    assert w.model == "codex"
    assert w.status == WorkerStatus.running
    assert w.worktree_path == "/wt/a"
    assert w.last_heartbeat is not None
    # secret never escapes into the serialized snapshot
    assert "LEAKED-SECRET" not in json.dumps(snap.model_dump(), default=str)


def test_unknown_status_falls_back_to_offline(tmp_path) -> None:
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"lanes": [{"id": "l2", "name": "x", "status": "weird"}]}))
    snap = SigmaLinkAdapter(str(p)).fetch_snapshot()
    assert snap.workers[0].status == WorkerStatus.offline


def test_malformed_json_is_unhealthy(tmp_path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not valid json")
    a = SigmaLinkAdapter(str(p))
    assert a.healthy() is False
    assert a.fetch_snapshot().workers == []
