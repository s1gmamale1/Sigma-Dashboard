from backend.app.hq.adapters.base import ControlPlaneSource, scrub
from backend.app.hq.adapters.mock import MockAdapter


def test_mock_snapshot_is_healthy_and_labeled() -> None:
    snap = MockAdapter().fetch_snapshot()
    assert snap.healthy is True
    assert snap.source == "mock"
    assert len(snap.workers) >= 1
    assert all(w.source == "mock" for w in snap.workers)
    assert all(p.source == "mock" for p in snap.projects)


def test_mock_satisfies_protocol() -> None:
    a = MockAdapter()
    assert isinstance(a, ControlPlaneSource)
    assert a.name == "mock"
    assert a.healthy() is True


def test_scrub_drops_secret_shaped_keys() -> None:
    out = scrub(
        {
            "name": "ok",
            "api_token": "X",
            "PASSWORD": "Y",
            "authorization": "Bearer z",
            "env": {"K": "V"},
            "cookie": "c",
            "value": 1,
        }
    )
    assert out == {"name": "ok", "value": 1}


def test_scrub_is_shallow_and_non_mutating() -> None:
    src = {"keep": 1, "secret": "s"}
    out = scrub(src)
    assert "secret" in src  # original untouched
    assert out == {"keep": 1}
