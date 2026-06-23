"""Signed, gated HQ control actions.

Gate order: auth → known action → enabled flag → secret configured → required
target → valid signoff (scope+target+nonce) → destructive flag → dry-run|execute.
Every attempt is audited. No real socket is touched (executor is faked); no
destructive action is executed live.
"""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from backend.app.config import Settings, get_settings
from backend.app.auth import require_edit
from backend.app.db import Base, get_db
from backend.app.models import AuditLog
from backend.app.main import app
from backend.app.hq import actions as actions_mod
from backend.app.hq.action_auth import NonceCache, mint_signoff

SECRET = "unit-test-hq-action-secret-32-bytes!"


class FakeExecutor:
    def __init__(self, result=None, fail=False):
        self.calls = []
        self._result = result if result is not None else {"ok": True, "result": {"id": "task-1"}}
        self._fail = fail

    def __call__(self, settings, spec, target):
        self.calls.append((spec.name, target))
        if self._fail:
            raise actions_mod.ActionExecError("socket unreachable")
        return self._result


def _client(settings: Settings, executor: FakeExecutor | None = None) -> tuple[TestClient, Session, FakeExecutor]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    ex = executor or FakeExecutor()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[require_edit] = lambda: "admin"
    nc = NonceCache()  # one cache per client (mirrors the process-singleton in prod)
    app.dependency_overrides[actions_mod.get_nonce_cache] = lambda: nc
    app.dependency_overrides[actions_mod.get_action_executor] = lambda: ex
    return TestClient(app), session, ex


def _enabled(**kw) -> Settings:
    return Settings(hq_allow_actions=True, hq_action_secret=SECRET, **kw)


def _signoff(action, target, nonce):
    return {"X-Sigma-Signoff": mint_signoff(SECRET, action, target, nonce=nonce)}


def test_requires_auth() -> None:
    client = TestClient(app)  # no auth override
    assert client.post("/api/v1/hq/actions/create_task", json={"target": {"title": "x"}}).status_code == 401


def test_unknown_action_404() -> None:
    client, _, _ = _client(_enabled())
    r = client.post("/api/v1/hq/actions/nope", json={"target": {}}, headers=_signoff("nope", {}, "z"))
    assert r.status_code == 404


def test_disabled_by_default_403() -> None:
    client, _, ex = _client(Settings())  # hq_allow_actions defaults False
    r = client.post("/api/v1/hq/actions/create_task", json={"target": {"title": "x"}})
    assert r.status_code == 403
    assert ex.calls == []


def test_enabled_but_no_secret_403() -> None:
    client, _, _ = _client(Settings(hq_allow_actions=True, hq_action_secret=""))
    r = client.post("/api/v1/hq/actions/create_task", json={"target": {"title": "x"}})
    assert r.status_code == 403


def test_missing_signoff_403() -> None:
    client, _, ex = _client(_enabled())
    r = client.post("/api/v1/hq/actions/create_task", json={"target": {"title": "x"}})
    assert r.status_code == 403
    assert ex.calls == []


def test_invalid_signoff_403() -> None:
    client, _, _ = _client(_enabled())
    r = client.post(
        "/api/v1/hq/actions/create_task",
        json={"target": {"title": "x"}},
        headers={"X-Sigma-Signoff": "garbage.token.here"},
    )
    assert r.status_code == 403


def test_missing_required_target_422() -> None:
    client, _, _ = _client(_enabled())
    target = {}  # create_task requires "title"
    r = client.post("/api/v1/hq/actions/create_task", json={"target": target}, headers=_signoff("create_task", target, "n-422"))
    assert r.status_code == 422


def test_dry_run_validated_not_executed(monkeypatch) -> None:
    client, session, ex = _client(_enabled())
    target = {"title": "ship it"}
    r = client.post(
        "/api/v1/hq/actions/create_task",
        json={"target": target, "dry_run": True},
        headers=_signoff("create_task", target, "n-dry"),
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["dry_run"] is True and body["status"] == "validated"
    assert body["would_invoke"] == "create_task"
    assert ex.calls == []  # executor NOT invoked on dry-run
    # audited
    rows = session.scalars(select(AuditLog).where(AuditLog.action == "hq.action.create_task")).all()
    assert len(rows) == 1 and '"dry_run": true' in rows[0].detail_json


def test_execute_invokes_socket_and_audits() -> None:
    client, session, ex = _client(_enabled())
    target = {"title": "real task"}
    r = client.post(
        "/api/v1/hq/actions/create_task",
        json={"target": target, "dry_run": False},
        headers=_signoff("create_task", target, "n-exec"),
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["status"] == "executed" and body["dry_run"] is False
    assert ex.calls == [("create_task", target)]
    rows = session.scalars(select(AuditLog).where(AuditLog.action == "hq.action.create_task")).all()
    assert any('"executed"' in r.detail_json for r in rows)


def test_execute_socket_failure_is_502_no_hidden_write() -> None:
    client, _, ex = _client(_enabled(), executor=FakeExecutor(fail=True))
    target = {"title": "will fail"}
    r = client.post(
        "/api/v1/hq/actions/create_task",
        json={"target": target, "dry_run": False},
        headers=_signoff("create_task", target, "n-fail"),
    )
    assert r.status_code == 502
    assert ex.calls == [("create_task", target)]  # attempted, failed deterministically


def test_destructive_blocked_without_destructive_flag() -> None:
    client, _, ex = _client(_enabled())  # hq_allow_destructive False
    target = {"sessionId": "s-1"}
    r = client.post(
        "/api/v1/hq/actions/stop_pane",
        json={"target": target, "dry_run": True},
        headers=_signoff("stop_pane", target, "n-dest"),
    )
    assert r.status_code == 403
    assert ex.calls == []


def test_destructive_dry_run_allowed_with_flag() -> None:
    client, _, ex = _client(_enabled(hq_allow_destructive=True))
    target = {"sessionId": "s-1"}
    r = client.post(
        "/api/v1/hq/actions/stop_pane",
        json={"target": target, "dry_run": True},
        headers=_signoff("stop_pane", target, "n-dest2"),
    )
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "validated"
    assert ex.calls == []  # dry-run never executes, destructive or not


def test_gate_rejects_replayed_nonce_over_http() -> None:
    """Replay rejection must be wired through the HTTP gate, not just verify_signoff()."""
    client, _, _ = _client(_enabled())
    target = {"title": "replay me"}
    hdr = _signoff("create_task", target, "n-http-replay")
    body = {"target": target, "dry_run": True}
    assert client.post("/api/v1/hq/actions/create_task", json=body, headers=hdr).status_code == 200
    # same token again → nonce already consumed → 403
    assert client.post("/api/v1/hq/actions/create_task", json=body, headers=hdr).status_code == 403


def test_gate_rejects_cross_action_retarget_over_http() -> None:
    """A signoff minted for action A must not authorize action B at the HTTP layer."""
    client, _, ex = _client(_enabled())
    target = {"sessionId": "s1", "prompt": "hi"}  # satisfies both read_pane and prompt_agent required
    hdr = {"X-Sigma-Signoff": mint_signoff(SECRET, "read_pane", target, nonce="n-xaction")}
    r = client.post("/api/v1/hq/actions/prompt_agent", json={"target": target, "dry_run": True}, headers=hdr)
    assert r.status_code == 403
    assert ex.calls == []


def test_no_secret_in_response_or_audit() -> None:
    client, session, _ = _client(_enabled())
    target = {"title": "x"}
    r = client.post(
        "/api/v1/hq/actions/create_task",
        json={"target": target, "dry_run": True},
        headers=_signoff("create_task", target, "n-leak"),
    )
    assert SECRET not in r.text
    rows = session.scalars(select(AuditLog)).all()
    assert all(SECRET not in row.detail_json for row in rows)
