"""Owner-added resilience tests for the SigmaLink live-socket path.

Complements test_sigmalink_adapter.py (mapping) and test_control_socket.py
(protocol). Focus: a configured-but-unreachable socket must degrade to an
unhealthy/empty snapshot — never raise — and an empty live payload is a healthy,
empty fleet.
"""

from backend.app.hq.adapters.control_socket import ControlSocketError
from backend.app.hq.adapters.sigmalink import SigmaLinkAdapter


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(
        "backend.app.hq.adapters.sigmalink.make_control_socket_client",
        lambda *_a, **_kw: client,
    )


def test_live_handshake_failure_degrades_to_unhealthy(monkeypatch) -> None:
    class FailingClient:
        def __enter__(self):
            raise ControlSocketError("handshake rejected")

        def __exit__(self, *_exc):
            return None

        def invoke(self, name):  # pragma: no cover - never reached
            raise AssertionError("must not invoke after failed handshake")

    _patch_client(monkeypatch, FailingClient())
    snap = SigmaLinkAdapter(None, socket_path="/sock", token="t").fetch_snapshot()
    assert snap.healthy is False
    assert snap.source == "sigmalink"
    assert snap.workers == [] and snap.sessions == [] and snap.projects == []


def test_live_transport_oserror_degrades_to_unhealthy(monkeypatch) -> None:
    class BrokenClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def invoke(self, name):
            raise OSError("broken pipe")

    _patch_client(monkeypatch, BrokenClient())
    snap = SigmaLinkAdapter(None, socket_path="/sock", token="t").fetch_snapshot()
    assert snap.healthy is False
    assert snap.workers == []


def test_live_empty_payload_is_healthy_and_empty(monkeypatch) -> None:
    class EmptyClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def invoke(self, name):
            return {"workspaces": []} if name == "list_workspaces" else {"sessions": []}

    _patch_client(monkeypatch, EmptyClient())
    snap = SigmaLinkAdapter(None, socket_path="/sock", token="t").fetch_snapshot()
    assert snap.healthy is True
    assert snap.workers == [] and snap.projects == [] and snap.swarms == []


def test_no_socket_and_no_file_is_unhealthy() -> None:
    snap = SigmaLinkAdapter(None).fetch_snapshot()
    assert snap.healthy is False
    assert snap.workers == []
