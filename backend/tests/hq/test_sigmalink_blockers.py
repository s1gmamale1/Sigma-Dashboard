"""Live blockers/alerts from the SigmaLink notification center.

get_app_state.state.notifications.recent is a real feed of
{id, kind, severity, title, createdAt(ms), readAt}. Error/warning entries map to
HQ Blockers (alerts); info is ignored. createdAt is epoch **milliseconds**.
"""

from backend.app.hq.adapters.sigmalink import SigmaLinkAdapter
from backend.app.hq.models import Severity


class _Client:
    def __init__(self, notifications):
        self._notifications = notifications

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def invoke(self, name):
        if name == "list_workspaces":
            return {"workspaces": []}
        if name == "list_active_sessions":
            return {"sessions": []}
        if name == "get_app_state":
            return {"ok": True, "state": {"notifications": {"recent": self._notifications}}}
        raise AssertionError(name)


def _adapter(monkeypatch, notifications):
    monkeypatch.setattr(
        "backend.app.hq.adapters.sigmalink.make_control_socket_client",
        lambda *_a, **_kw: _Client(notifications),
    )
    return SigmaLinkAdapter(None, socket_path="/sock", token="t")


def test_error_and_warning_notifications_become_blockers(monkeypatch) -> None:
    notifs = [
        {"id": "n1", "kind": "pty-exit", "severity": "error", "title": "Pane crashed", "createdAt": 1782166957400, "readAt": None},
        {"id": "n2", "kind": "review", "severity": "warning", "title": "Needs review", "createdAt": 1782166000000, "readAt": 1782166900000},
        {"id": "n3", "kind": "info", "severity": "info", "title": "Pane exited (0)", "createdAt": 1782160000000, "readAt": None},
    ]
    snap = _adapter(monkeypatch, notifs).fetch_snapshot()
    assert snap.healthy is True
    by_id = {b.source_id: b for b in snap.blockers}
    assert set(by_id) == {"n1", "n2"}  # info excluded
    assert by_id["n1"].severity == Severity.high
    assert by_id["n1"].status == "open"          # unread
    assert by_id["n1"].opened_at is not None and by_id["n1"].opened_at.year == 2026  # ms parsed, not year 58k
    assert by_id["n2"].severity == Severity.medium
    assert by_id["n2"].status == "resolved"      # readAt set


def test_no_notifications_means_no_blockers(monkeypatch) -> None:
    snap = _adapter(monkeypatch, []).fetch_snapshot()
    assert snap.healthy is True
    assert snap.blockers == []


def test_get_app_state_failure_does_not_sink_snapshot(monkeypatch) -> None:
    class PartialClient:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def invoke(self, name):
            if name == "get_app_state":
                raise RuntimeError("state unavailable")
            return {"workspaces": []} if name == "list_workspaces" else {"sessions": []}

    monkeypatch.setattr(
        "backend.app.hq.adapters.sigmalink.make_control_socket_client",
        lambda *_a, **_kw: PartialClient(),
    )
    snap = SigmaLinkAdapter(None, socket_path="/sock", token="t").fetch_snapshot()
    assert snap.healthy is True   # workers/sessions still fetched
    assert snap.blockers == []    # blockers best-effort, degrade quietly
