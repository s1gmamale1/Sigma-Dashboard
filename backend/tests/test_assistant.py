import asyncio
import json

import pytest

from backend.app import assistant
from backend.app.config import Settings


def test_gateway_session_key_is_three_part():
    s = Settings(gateway_agent="viper", gateway_session="dashboard")
    assert s.gateway_session_key == "agent:viper:dashboard"


def test_enabled_assistant_requires_real_token():
    s = Settings(assistant_enabled=True, gateway_token="")
    with pytest.raises(Exception):
        s.validate_runtime_secrets()


class FakeWS:
    """Scripts server frames for one connection; records what the client sent."""
    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def recv(self):
        if not self._frames:
            raise RuntimeError("no more frames")
        return self._frames.pop(0)

    async def send(self, data):
        self.sent.append(json.loads(data))


async def _collect(agen):
    return [item async for item in agen]


def test_gateway_client_streams_run_delta_final(monkeypatch):
    frames = [
        json.dumps({"event": "connect.challenge", "payload": {"nonce": "n"}}),
        json.dumps({"type": "res", "id": "c1", "ok": True, "payload": {"type": "hello-ok"}}),
        json.dumps({"type": "res", "id": "r1", "ok": True, "payload": {"runId": "run_9"}}),
        json.dumps({"type": "event", "event": "chat", "payload": {"state": "delta", "deltaText": "Hi"}}),
        json.dumps({"type": "event", "event": "chat", "payload": {"state": "final", "stopReason": "end_turn"}}),
    ]
    fake = FakeWS(frames)
    monkeypatch.setattr(assistant.websockets, "connect", lambda *a, **k: fake)

    client = assistant.GatewayClient(Settings(gateway_token="x" * 32, assistant_enabled=True))
    out = asyncio.run(_collect(client.stream_chat("hi")))

    assert [e["kind"] for e in out] == ["run", "delta", "final"]
    # handshake: first client frame is the connect request with the token
    assert fake.sent[0]["method"] == "connect"
    assert fake.sent[0]["params"]["auth"]["token"] == "x" * 32
    # second client frame is chat.send with the 3-part session key + idempotencyKey
    assert fake.sent[1]["method"] == "chat.send"
    assert fake.sent[1]["params"]["sessionKey"] == "agent:viper:dashboard"
    assert fake.sent[1]["params"]["idempotencyKey"]


from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth import require_edit
from backend.app.config import get_settings


class FakeClient:
    def __init__(self, events):
        self._events = events
        self.aborted = None
        self.last_session_key = None
        self.last_abort_session_key = None

    async def stream_chat(self, prompt, session_key=None):
        self.last_session_key = session_key
        for e in self._events:
            yield e

    async def abort(self, run_id, session_key=None):
        self.aborted = run_id
        self.last_abort_session_key = session_key


_TEST_SETTINGS = dict(
    jwt_secret="unit-test-jwt-secret-0123456789",
    viper_token="unit-test-viper-token-0123456789",
    gateway_token="x" * 32,
)


def _override(events=None, enabled=True, role="manager"):
    app.dependency_overrides[assistant.get_gateway_client] = lambda: FakeClient(events or [])
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role=role)
    app.dependency_overrides[get_settings] = lambda: Settings(
        assistant_enabled=enabled, **_TEST_SETTINGS)


def test_chat_streams_sse():
    _override(events=[
        {"kind": "run", "runId": "run_1"},
        {"kind": "delta", "text": "Hel"},
        {"kind": "delta", "text": "lo"},
        {"kind": "final", "stopReason": "end_turn"},
    ])
    try:
        c = TestClient(app)
        with c.stream("POST", "/api/v1/assistant/chat", json={"message": "hi"}) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            body = "".join(r.iter_text())
        events = [json.loads(ln[6:]) for ln in body.splitlines() if ln.startswith("data: ")]
        assert [e["kind"] for e in events] == ["run", "delta", "delta", "final"]
    finally:
        app.dependency_overrides.clear()


def test_chat_disabled_returns_503():
    _override(enabled=False)
    try:
        c = TestClient(app)
        r = c.post("/api/v1/assistant/chat", json={"message": "hi"})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_abort_calls_client():
    fake = FakeClient([])
    app.dependency_overrides[assistant.get_gateway_client] = lambda: fake
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role="admin")
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, **_TEST_SETTINGS)
    try:
        c = TestClient(app)
        r = c.post("/api/v1/assistant/abort", json={"run_id": "run_1"})
        assert r.status_code == 200
        assert r.json()["data"]["aborted"] is True
        assert fake.aborted == "run_1"
    finally:
        app.dependency_overrides.clear()


def test_chat_rejects_viewer_role():
    # Do NOT override require_edit — exercise the real gate with a viewer JWT.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from backend.app.db import Base, get_db
    from backend.app.auth import create_access_token
    # Mirror backend/tests/test_users.py for seeding + user-creation pattern
    from backend.app.bootstrap import seed_db
    from backend.app.models import User as UserModel
    from backend.app.auth import hash_password

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    settings = Settings(**_TEST_SETTINGS)
    viewer = UserModel(
        username="viewer1",
        display_name="Viewer One",
        role="viewer",
        active=True,
        password_hash=hash_password("viewerpass"),
        must_change_password=False,
    )
    session.add(viewer)
    session.commit()
    token = create_access_token(settings, "viewer1", "viewer")[0]

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, **_TEST_SETTINGS)
    try:
        c = TestClient(app)
        r = c.post(
            "/api/v1/assistant/chat",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_gateway_client_surfaces_chat_send_rejection(monkeypatch):
    # A gateway rejection (res ok:false, no runId) must terminate immediately
    # with the real error — not stall until the idle timeout reporting "timeout".
    frames = [
        json.dumps({"event": "connect.challenge", "payload": {"nonce": "n"}}),
        json.dumps({"type": "res", "id": "c1", "ok": True, "payload": {"type": "hello-ok"}}),
        json.dumps({"type": "res", "id": "r1", "ok": False,
                    "error": {"code": "INVALID_REQUEST", "message": "missing scope: operator.write"}}),
    ]
    fake = FakeWS(frames)
    monkeypatch.setattr(assistant.websockets, "connect", lambda *a, **k: fake)
    client = assistant.GatewayClient(Settings(gateway_token="x" * 32, assistant_enabled=True))
    out = asyncio.run(_collect(client.stream_chat("hi")))
    assert [e["kind"] for e in out] == ["error"]
    assert "operator.write" in out[0]["message"]
    assert out[0]["errorKind"] == "INVALID_REQUEST"


def test_chat_rejects_empty_message():
    _override()
    try:
        c = TestClient(app)
        r = c.post("/api/v1/assistant/chat", json={"message": ""})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


# --- Session management tests ---

def test_chat_request_defaults_session_to_dashboard():
    from backend.app.assistant import ChatRequest
    req = ChatRequest(message="hi")
    assert req.session == "dashboard"


def test_abort_request_defaults_session_to_dashboard():
    from backend.app.assistant import AbortRequest
    req = AbortRequest(run_id="run_1")
    assert req.session == "dashboard"


def test_chat_request_rejects_colon_in_session():
    """A session value with a colon must fail validation (would escape the agent prefix)."""
    c = TestClient(app)
    # no auth overrides needed — validation fires before auth
    _override()
    try:
        r = c.post("/api/v1/assistant/chat", json={"message": "hi", "session": "a:b"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_request_rejects_path_traversal_in_session():
    c = TestClient(app)
    _override()
    try:
        r = c.post("/api/v1/assistant/chat", json={"message": "hi", "session": "../x"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_abort_request_rejects_colon_in_session():
    _override()
    try:
        c = TestClient(app)
        r = c.post("/api/v1/assistant/abort", json={"run_id": "run_1", "session": "a:b"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_chat_with_custom_session_sends_correct_key_to_gateway(monkeypatch):
    """chat.send must carry sessionKey = agent:viper:<session> when session is overridden."""
    frames = [
        json.dumps({"event": "connect.challenge", "payload": {"nonce": "n"}}),
        json.dumps({"type": "res", "id": "c1", "ok": True, "payload": {"type": "hello-ok"}}),
        json.dumps({"type": "res", "id": "r1", "ok": True, "payload": {"runId": "run_42"}}),
        json.dumps({"type": "event", "event": "chat", "payload": {"state": "final", "stopReason": "end_turn"}}),
    ]
    fake = FakeWS(frames)
    monkeypatch.setattr(assistant.websockets, "connect", lambda *a, **k: fake)

    client = assistant.GatewayClient(Settings(gateway_token="x" * 32, assistant_enabled=True))
    out = asyncio.run(_collect(client.stream_chat("hi", session_key="agent:viper:dashboard-xyz")))

    assert [e["kind"] for e in out] == ["run", "final"]
    # chat.send frame must carry the custom session key
    chat_send = next(f for f in fake.sent if f.get("method") == "chat.send")
    assert chat_send["params"]["sessionKey"] == "agent:viper:dashboard-xyz"


def test_route_resolves_session_key_for_custom_session():
    """The route must pass the resolved session key to the client when session is overridden."""
    fake = FakeClient(events=[
        {"kind": "run", "runId": "run_x"},
        {"kind": "final", "stopReason": "end_turn"},
    ])
    app.dependency_overrides[assistant.get_gateway_client] = lambda: fake
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role="manager")
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, **_TEST_SETTINGS)
    try:
        c = TestClient(app)
        with c.stream("POST", "/api/v1/assistant/chat", json={"message": "hi", "session": "dashboard-xyz"}) as r:
            assert r.status_code == 200
            list(r.iter_text())  # drain
        assert fake.last_session_key == "agent:viper:dashboard-xyz"
    finally:
        app.dependency_overrides.clear()


def test_route_resolves_session_key_for_abort():
    """abort route must pass the resolved session key to the client."""
    fake = FakeClient([])
    app.dependency_overrides[assistant.get_gateway_client] = lambda: fake
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role="admin")
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, **_TEST_SETTINGS)
    try:
        c = TestClient(app)
        r = c.post("/api/v1/assistant/abort", json={"run_id": "run_1", "session": "dashboard-xyz"})
        assert r.status_code == 200
        assert fake.last_abort_session_key == "agent:viper:dashboard-xyz"
    finally:
        app.dependency_overrides.clear()
