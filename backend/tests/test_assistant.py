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

    async def stream_chat(self, prompt):
        for e in self._events:
            yield e

    async def abort(self, run_id):
        self.aborted = run_id


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
