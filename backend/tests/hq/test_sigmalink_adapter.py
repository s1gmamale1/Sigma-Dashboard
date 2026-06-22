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


def test_live_socket_payload_maps_workspaces_sessions_and_swarms(monkeypatch) -> None:
    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def invoke(self, name):
            if name == "list_workspaces":
                return {
                    "workspaces": [
                        {
                            "id": "ws-1",
                            "name": "SigmaDevelopment",
                            "rootPath": "/repo",
                            "active": True,
                        }
                    ]
                }
            if name == "list_active_sessions":
                return {
                    "sessions": [
                        {
                            "sessionId": "s-agent",
                            "name": "Sage",
                            "provider": "claude",
                            "status": "running",
                            "agentKey": "builder-6",
                            "swarmId": "swarm-1",
                        },
                        {
                            "sessionId": "s-shell",
                            "name": "Shell",
                            "provider": "shell",
                            "status": "running",
                        },
                    ]
                }
            raise AssertionError(name)

    monkeypatch.setattr(
        "backend.app.hq.adapters.sigmalink.make_control_socket_client",
        lambda *_a, **_kw: FakeClient(),
    )
    snap = SigmaLinkAdapter(None, socket_path="/sock", token="secret").fetch_snapshot()
    assert snap.healthy is True
    assert [p.id for p in snap.projects] == ["sigmalink:ws-1"]
    assert [w.id for w in snap.workers] == ["sigmalink:builder-6"]
    assert {s.id: s.worker_id for s in snap.sessions} == {
        "sigmalink:s-agent": "sigmalink:builder-6",
        "sigmalink:s-shell": None,
    }
    assert snap.swarms[0].id == "sigmalink:swarm-1"
    assert snap.swarms[0].member_worker_ids == ["sigmalink:builder-6"]
    assert "secret" not in json.dumps(snap.model_dump(), default=str)


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
