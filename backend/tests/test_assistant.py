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
