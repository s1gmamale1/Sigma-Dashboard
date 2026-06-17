# Viper Live Chat (Ask Viper Dock) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admins+managers-only "Ask Viper" chat dock to the Sigma Dashboard that streams live replies from the existing `viper` OpenClaw agent via a backend gateway proxy.

**Architecture:** A new FastAPI sub-router (`assistant.py`) opens a server-side WebSocket to the OpenClaw gateway (`ws://127.0.0.1:18789`, protocol v4), performs the challenge-first token handshake, issues `chat.send` to the isolated `agent:viper:dashboard` session, and relays the single multiplexed `chat` event back to the browser as Server-Sent Events. The React frontend reads the SSE stream with `fetch` + `ReadableStream` (so it can send the `Authorization` header) and renders it in a living-orb → glass-panel dock.

**Tech Stack:** FastAPI · `websockets` (new dep) · pytest/TestClient · React 18 + TypeScript + Vite · TanStack Query · token-driven CSS (glass + sigma-orb).

**Reference spec:** `docs/VIPER_CHAT_PLAN.md` (v2). Read §3 (real wire format) and §6 (safety) before starting.

**Branch:** `viper-chat` (already created).

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/viper_chat_spike.py` | create | Phase 0 throwaway: prove handshake + `chat.send` + streaming end-to-end |
| `requirements.txt` | modify | add `websockets` client dependency |
| `backend/app/config.py` | modify | gateway settings + `gateway_session_key` + secret guard |
| `backend/app/assistant.py` | create | `GatewayClient` (WS proxy) + `/assistant/chat` (SSE) + `/assistant/abort` |
| `backend/app/main.py` | modify | `include_router(assistant_router)` |
| `backend/tests/test_assistant.py` | create | auth gating, SSE framing, abort, disabled flag, protocol logic |
| `frontend/src/lib/api.ts` | modify | `streamAssistant()` + `abortAssistant()` |
| `frontend/src/components/ViperOrb.tsx` | create | living orb button (idle/streaming state) |
| `frontend/src/components/AssistantDock.tsx` | create | orb → glass panel, message list, input, Stop |
| `frontend/src/styles/views/assistant.css` | create | dock glass + orb rim-lights + reduced-motion |
| `frontend/src/styles/index.css` | modify | `@import` the new view stylesheet |
| `frontend/src/App.tsx` | modify | mount `<AssistantDock>` for admins+managers |

**Out of this plan (owned by Viper's manager):** the OpenClaw-side read-only persona / tool governance — see spec §9. Task 13 is the handoff.

---

## Task 1: Phase 0 spike — prove the gateway protocol

**Files:**
- Create: `scripts/viper_chat_spike.py`
- Modify: `requirements.txt`

This de-risks everything: if any protocol detail from the recon is off (e.g. the valid `client.id` enum value), we discover it here for the cost of one script — before any real code depends on it.

- [ ] **Step 1: Add the `websockets` dependency**

Edit `requirements.txt`, append:

```
websockets==14.1
```

- [ ] **Step 2: Install it into the app venv**

Run: `cd ~/sigma-dashboard && .venv/bin/pip install websockets==14.1`
Expected: installs cleanly. If it fails on Python 3.14, run `.venv/bin/pip install websockets` and pin the resolved version in `requirements.txt` instead.

- [ ] **Step 3: Write the spike script**

Create `scripts/viper_chat_spike.py`:

```python
"""Phase 0 spike: prove the OpenClaw gateway chat path end-to-end.

Run:  cd ~/sigma-dashboard && .venv/bin/python scripts/viper_chat_spike.py "who is at risk this week?"

Reads the gateway token from ~/.openclaw/openclaw.json (gateway.auth.token).
Connects, does the challenge-first token handshake, sends one chat.send to the
isolated agent:viper:dashboard session, and prints streamed deltas until final.
No dashboard, no UI. Throwaway — delete after the protocol is confirmed.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import uuid

import websockets

WS_URL = "ws://127.0.0.1:18789"
SESSION_KEY = "agent:viper:dashboard"
OPENCLAW_JSON = pathlib.Path.home() / ".openclaw" / "openclaw.json"
# Must be a valid id from the gateway's client-info enum. "webchat-ui" is the
# documented example; if connect is rejected, try another valid id.
CLIENT_ID = "webchat-ui"


def load_token() -> str:
    cfg = json.loads(OPENCLAW_JSON.read_text())
    return cfg["gateway"]["auth"]["token"]


async def main(prompt: str) -> None:
    token = load_token()
    async with websockets.connect(WS_URL, max_size=None) as ws:
        # 1. Server pushes connect.challenge first (token auth ignores the nonce).
        first = json.loads(await ws.recv())
        assert first.get("event") == "connect.challenge", first
        # 2. Reply with the connect request.
        await ws.send(json.dumps({
            "type": "req", "id": "c1", "method": "connect",
            "params": {
                "minProtocol": 4, "maxProtocol": 4,
                "client": {"id": CLIENT_ID, "version": "0.0.1",
                           "platform": "backend", "mode": "backend"},
                "role": "operator",
                "scopes": ["operator.read", "operator.write"],
                "auth": {"token": token},
            },
        }))
        hello = json.loads(await ws.recv())
        assert hello.get("ok"), hello
        print("[connected]", hello.get("payload", {}).get("type"))
        # 3. Send one turn.
        await ws.send(json.dumps({
            "type": "req", "id": "r1", "method": "chat.send",
            "params": {"sessionKey": SESSION_KEY, "message": prompt,
                       "idempotencyKey": str(uuid.uuid4())},
        }))
        # 4. Read frames until the chat turn is terminal.
        async for raw in ws:
            frame = json.loads(raw)
            if frame.get("type") == "res" and frame.get("id") == "r1":
                print("[runId]", frame.get("payload", {}).get("runId"))
                continue
            if frame.get("event") != "chat":
                continue
            p = frame.get("payload", {})
            state = p.get("state")
            if state == "delta":
                sys.stdout.write(p.get("deltaText", "")); sys.stdout.flush()
            elif state == "final":
                print("\n[final]", p.get("stopReason"), p.get("usage")); return
            elif state == "error":
                print("\n[error]", p.get("errorKind"), p.get("errorMessage")); return
            elif state == "aborted":
                print("\n[aborted]"); return


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Say hello in one short sentence."))
```

- [ ] **Step 4: Run the spike**

Run: `cd ~/sigma-dashboard && .venv/bin/python scripts/viper_chat_spike.py "say hello in one sentence"`
Expected: `[connected] hello-ok`, then a `[runId] ...`, then Viper's answer streams token-by-token, then `[final] end_turn ...`.

If `connect` is rejected: the `CLIENT_ID` enum value is wrong — grep `/opt/homebrew/lib/node_modules/openclaw/dist/client-info-*.js` for valid ids and retry. **Record the confirmed `CLIENT_ID` — Task 4 uses it.**

- [ ] **Step 5: Commit**

```bash
cd ~/sigma-dashboard
git add requirements.txt scripts/viper_chat_spike.py
git commit -m "spike(assistant): prove OpenClaw gateway chat path end-to-end"
```

---

## Task 2: Backend config — gateway settings + secret guard

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_assistant.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_assistant.py` with:

```python
import pytest

from backend.app.config import Settings


def test_gateway_session_key_is_three_part():
    s = Settings(gateway_agent="viper", gateway_session="dashboard")
    assert s.gateway_session_key == "agent:viper:dashboard"


def test_enabled_assistant_requires_real_token():
    s = Settings(assistant_enabled=True, gateway_token="")
    with pytest.raises(Exception):
        s.validate_runtime_secrets()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py -v`
Expected: FAIL — `Settings` has no `gateway_session_key` / fields.

- [ ] **Step 3: Add the settings + property + guard**

Read `backend/app/config.py` first (Settings class ~line 8, `validate_runtime_secrets` ~line 47). Add these fields to the `Settings` class body (alongside the existing fields, above `model_config`):

```python
    gateway_ws_url: str = "ws://127.0.0.1:18789"
    gateway_token: str = ""
    gateway_agent: str = "viper"
    gateway_session: str = "dashboard"
    assistant_enabled: bool = False
    assistant_idle_timeout_s: float = 120.0
```

Add this property to the `Settings` class:

```python
    @property
    def gateway_session_key(self) -> str:
        return f"agent:{self.gateway_agent}:{self.gateway_session}"
```

Inside the existing `validate_runtime_secrets(self)` method, add this check (match the method's existing raise style — reuse whatever exception/message pattern it already uses for bad secrets):

```python
        if self.assistant_enabled and len(self.gateway_token) < 16:
            raise ValueError(
                "SIGMA_GATEWAY_TOKEN must be set (>=16 chars) when SIGMA_ASSISTANT_ENABLED is true"
            )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/sigma-dashboard
git add backend/app/config.py backend/tests/test_assistant.py
git commit -m "feat(assistant): gateway settings + enabled-token guard"
```

---

## Task 3: `GatewayClient` — the WS proxy (protocol logic)

**Files:**
- Create: `backend/app/assistant.py`
- Test: `backend/tests/test_assistant.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_assistant.py`:

```python
import asyncio
import json

from backend.app import assistant
from backend.app.config import Settings


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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py::test_gateway_client_streams_run_delta_final -v`
Expected: FAIL — `backend.app.assistant` does not exist.

- [ ] **Step 3: Create `assistant.py` with `GatewayClient`**

Create `backend/app/assistant.py`:

```python
"""Server-side proxy to the OpenClaw gateway chat control plane.

Holds the gateway token (never sent to the browser), performs the challenge-first
token handshake, and relays the single multiplexed `chat` event as normalized
dict events. See docs/VIPER_CHAT_PLAN.md §3 for the wire format.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import websockets

from .config import Settings

# Confirmed by the Phase 0 spike: must be the Control-UI operator id + webchat
# mode + a loopback Origin header, or the gateway denies operator.write on chat.send.
CLIENT_ID = "openclaw-control-ui"
CLIENT_MODE = "webchat"
GATEWAY_ORIGIN = "http://127.0.0.1"


class GatewayClient:
    def __init__(self, settings: Settings) -> None:
        self._url = settings.gateway_ws_url
        self._token = settings.gateway_token
        self._session_key = settings.gateway_session_key
        self._idle_timeout = settings.assistant_idle_timeout_s

    @asynccontextmanager
    async def _open(self) -> AsyncIterator[Any]:
        async with websockets.connect(self._url, max_size=None,
                                      additional_headers={"Origin": GATEWAY_ORIGIN}) as ws:
            challenge = json.loads(await ws.recv())
            if challenge.get("event") != "connect.challenge":
                raise RuntimeError(f"unexpected first frame: {challenge}")
            await ws.send(json.dumps({
                "type": "req", "id": "c1", "method": "connect",
                "params": {
                    "minProtocol": 4, "maxProtocol": 4,
                    "client": {"id": CLIENT_ID, "version": "1.0.0",
                               "platform": "backend", "mode": CLIENT_MODE},
                    "role": "operator",
                    "scopes": ["operator.read", "operator.write"],
                    "auth": {"token": self._token},
                },
            }))
            hello = json.loads(await ws.recv())
            if not hello.get("ok"):
                raise RuntimeError(f"gateway connect failed: {hello.get('error')}")
            yield ws

    async def stream_chat(self, prompt: str) -> AsyncIterator[dict]:
        async with self._open() as ws:
            await ws.send(json.dumps({
                "type": "req", "id": "r1", "method": "chat.send",
                "params": {"sessionKey": self._session_key, "message": prompt,
                           "idempotencyKey": str(uuid.uuid4())},
            }))
            run_id: str | None = None
            while True:
                try:
                    async with asyncio.timeout(self._idle_timeout):
                        raw = await ws.recv()
                except (TimeoutError, asyncio.TimeoutError):
                    if run_id:
                        await self._abort_on(ws, run_id)
                    yield {"kind": "error", "message": "timeout"}
                    return
                except websockets.ConnectionClosed:
                    yield {"kind": "error", "message": "connection closed"}
                    return
                frame = json.loads(raw)
                if frame.get("type") == "res" and frame.get("id") == "r1":
                    run_id = frame.get("payload", {}).get("runId")
                    if run_id:
                        yield {"kind": "run", "runId": run_id}
                    continue
                if frame.get("event") != "chat":
                    continue
                p = frame.get("payload", {})
                state = p.get("state")
                if state == "delta":
                    yield {"kind": "delta", "text": p.get("deltaText", "")}
                elif state == "final":
                    yield {"kind": "final", "stopReason": p.get("stopReason")}
                    return
                elif state == "error":
                    yield {"kind": "error", "message": p.get("errorMessage", "error"),
                           "errorKind": p.get("errorKind")}
                    return
                elif state == "aborted":
                    yield {"kind": "aborted"}
                    return

    async def _abort_on(self, ws: Any, run_id: str) -> None:
        await ws.send(json.dumps({
            "type": "req", "id": "a1", "method": "chat.abort",
            "params": {"sessionKey": self._session_key, "runId": run_id},
        }))

    async def abort(self, run_id: str) -> None:
        async with self._open() as ws:
            await self._abort_on(ws, run_id)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py -v`
Expected: PASS (all tests so far).

- [ ] **Step 5: Commit**

```bash
cd ~/sigma-dashboard
git add backend/app/assistant.py backend/tests/test_assistant.py
git commit -m "feat(assistant): GatewayClient WS proxy with normalized chat events"
```

---

## Task 4: SSE route `POST /api/v1/assistant/chat`

**Files:**
- Modify: `backend/app/assistant.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_assistant.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_assistant.py`:

```python
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


def _override(events=None, enabled=True, role="manager"):
    app.dependency_overrides[assistant.get_gateway_client] = lambda: FakeClient(events or [])
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role=role)
    app.dependency_overrides[get_settings] = lambda: Settings(
        assistant_enabled=enabled, gateway_token="x" * 32)


def test_chat_streams_sse():
    _override(events=[
        {"kind": "run", "runId": "run_1"},
        {"kind": "delta", "text": "Hel"},
        {"kind": "delta", "text": "lo"},
        {"kind": "final", "stopReason": "end_turn"},
    ])
    try:
        with TestClient(app) as c:
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
        with TestClient(app) as c:
            r = c.post("/api/v1/assistant/chat", json={"message": "hi"})
        assert r.status_code == 503
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py::test_chat_streams_sse -v`
Expected: FAIL — `assistant.get_gateway_client` / route do not exist.

- [ ] **Step 3: Add the router, dependency, and route**

Append to `backend/app/assistant.py` (add the imports at the top alongside the existing ones):

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import require_edit
from .config import get_settings
from .models import User
from .schemas import Envelope


class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}
    message: str


class AbortRequest(BaseModel):
    model_config = {"extra": "forbid"}
    run_id: str


def get_gateway_client(settings: Settings = Depends(get_settings)) -> GatewayClient:
    return GatewayClient(settings)


router = APIRouter(prefix="/api/v1", tags=["Assistant"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/assistant/chat")
async def assistant_chat(
    payload: ChatRequest,
    settings: Settings = Depends(get_settings),
    client: GatewayClient = Depends(get_gateway_client),
    _user: User = Depends(require_edit),
) -> StreamingResponse:
    if not settings.assistant_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Assistant is disabled")

    async def gen() -> AsyncIterator[str]:
        try:
            async for event in client.stream_chat(payload.message):
                yield _sse(event)
        except Exception as exc:  # surface any failure as a terminal SSE error
            yield _sse({"kind": "error", "message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Then modify `backend/app/main.py` — after the existing `app.include_router(router)` line, add:

```python
    from .assistant import router as assistant_router
    app.include_router(assistant_router)
```

(Place it in the same scope as the existing `include_router`. If `main.py` imports routers at module top, mirror that style instead.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py -v`
Expected: PASS (stream + disabled).

- [ ] **Step 5: Commit**

```bash
cd ~/sigma-dashboard
git add backend/app/assistant.py backend/app/main.py backend/tests/test_assistant.py
git commit -m "feat(assistant): admin/manager-gated SSE chat route"
```

---

## Task 5: Abort route + real auth-gating test

**Files:**
- Modify: `backend/app/assistant.py`
- Test: `backend/tests/test_assistant.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_assistant.py`:

```python
def test_abort_calls_client():
    fake = FakeClient([])
    app.dependency_overrides[assistant.get_gateway_client] = lambda: fake
    app.dependency_overrides[require_edit] = lambda: SimpleNamespace(username="u", role="admin")
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, gateway_token="x" * 32)
    try:
        with TestClient(app) as c:
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
    # NOTE: align the next two imports/calls with backend/tests/test_users.py
    from backend.app.bootstrap import seed_db
    from backend.app.models import User as UserModel

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_db(session)
    settings = get_settings()
    viewer = UserModel(username="viewer1", role="viewer", active=True,
                       password_hash="x", must_change_password=False)
    session.add(viewer)
    session.commit()
    token = create_access_token(settings, "viewer1")[0]

    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(assistant_enabled=True, gateway_token="x" * 32)
    try:
        with TestClient(app) as c:
            r = c.post("/api/v1/assistant/chat",
                       json={"message": "hi"},
                       headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()
```

> If `seed_db` / `User(...)` field names differ, open `backend/tests/test_users.py` and copy its exact seeding + user-creation lines (it does precisely this). The assertion (`viewer → 403`) does not change.

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/test_assistant.py::test_abort_calls_client -v`
Expected: FAIL — `/assistant/abort` route missing.

- [ ] **Step 3: Add the abort route**

Append to `backend/app/assistant.py`:

```python
@router.post("/assistant/abort", response_model=Envelope)
async def assistant_abort(
    payload: AbortRequest,
    settings: Settings = Depends(get_settings),
    client: GatewayClient = Depends(get_gateway_client),
    _user: User = Depends(require_edit),
) -> Envelope:
    if not settings.assistant_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Assistant is disabled")
    await client.abort(payload.run_id)
    return Envelope(data={"aborted": True})
```

- [ ] **Step 4: Run the full backend suite**

Run: `cd ~/sigma-dashboard && .venv/bin/python -m pytest backend/tests/ -v`
Expected: PASS — including the existing suites (no regressions). If `test_api_contract.py` fails because it snapshots the OpenAPI schema, regenerate per its in-file instructions (commonly `npm run generate:api` then re-run), since two new paths were added.

- [ ] **Step 5: Commit**

```bash
cd ~/sigma-dashboard
git add backend/app/assistant.py backend/tests/test_assistant.py
git commit -m "feat(assistant): abort route + viewer-role rejection test"
```

---

## Task 6: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/src/lib/openapi.d.ts` (generated)

- [ ] **Step 1: Regenerate**

Run: `cd ~/sigma-dashboard/frontend && npm run generate:api`
Expected: `openapi.d.ts` updates to include `/api/v1/assistant/chat` and `/api/v1/assistant/abort`.

- [ ] **Step 2: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/lib/openapi.d.ts frontend/src/lib/openapi.json
git commit -m "chore(assistant): regenerate OpenAPI types"
```

---

## Task 7: Frontend streaming client (`api.ts`)

**Files:**
- Modify: `frontend/src/lib/api.ts`

No FE test runner exists; the gate is `tsc` + `vite build`.

- [ ] **Step 1: Add the streaming helpers**

Append to `frontend/src/lib/api.ts` (it already exports `apiFetchEnvelope`):

```ts
export type AssistantEvent =
  | { kind: "run"; runId: string }
  | { kind: "delta"; text: string }
  | { kind: "final"; stopReason?: string }
  | { kind: "error"; message: string; errorKind?: string }
  | { kind: "aborted" };

export async function streamAssistant(
  token: string | null,
  message: string,
  onEvent: (event: AssistantEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/v1/assistant/chat", {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) throw new Error(`Assistant request failed (${res.status})`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(6)) as AssistantEvent);
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}

export async function abortAssistant(token: string | null, runId: string): Promise<void> {
  await apiFetchEnvelope<{ aborted: boolean }>("/api/v1/assistant/abort", token, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  });
}
```

- [ ] **Step 2: Verify the build**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: `tsc -b && vite build` completes with no type errors.

- [ ] **Step 3: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/lib/api.ts
git commit -m "feat(assistant): streamAssistant + abortAssistant client helpers"
```

---

## Task 8: `ViperOrb` component

**Files:**
- Create: `frontend/src/components/ViperOrb.tsx`

- [ ] **Step 1: Create the orb**

Create `frontend/src/components/ViperOrb.tsx`:

```tsx
import { useReducedMotion } from "../hooks/useReducedMotion";

export function ViperOrb({
  state,
  onClick,
  label,
}: {
  state: "idle" | "streaming";
  onClick?: () => void;
  label: string;
}) {
  const reduced = useReducedMotion();
  return (
    <button
      type="button"
      className="viper-orb"
      data-state={state}
      data-reduced={reduced ? "true" : "false"}
      onClick={onClick}
      aria-label={label}
    >
      <span className="viper-orb__core" aria-hidden="true" />
      <span className="viper-orb__rim" aria-hidden="true" />
    </button>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: passes. (`ViperOrb` is unused for now — that's fine; Task 9 consumes it. If `noUnusedLocals` flags it, skip the standalone build here and verify at Task 9.)

- [ ] **Step 3: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/components/ViperOrb.tsx
git commit -m "feat(assistant): living ViperOrb component"
```

---

## Task 9: `AssistantDock` component

**Files:**
- Create: `frontend/src/components/AssistantDock.tsx`

- [ ] **Step 1: Create the dock**

Create `frontend/src/components/AssistantDock.tsx`:

```tsx
import { useRef, useState } from "react";
import { streamAssistant, abortAssistant, type AssistantEvent } from "../lib/api";
import { ViperOrb } from "./ViperOrb";

type Msg = { role: "you" | "viper"; text: string };

const CHIPS = ["Who's at risk this week?", "This week's lateness", "Summarize Aiden's month"];

export function AssistantDock({ token }: { token: string | null }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const runIdRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  async function send(text: string) {
    const q = text.trim();
    if (!q || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "you", text: q }, { role: "viper", text: "" }]);
    setStreaming(true);
    runIdRef.current = null;
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const appendToViper = (chunk: string) =>
      setMessages((m) => {
        const next = m.slice();
        const last = next[next.length - 1];
        if (last && last.role === "viper") next[next.length - 1] = { ...last, text: last.text + chunk };
        return next;
      });

    try {
      await streamAssistant(
        token,
        q,
        (e: AssistantEvent) => {
          if (e.kind === "run") runIdRef.current = e.runId;
          else if (e.kind === "delta") appendToViper(e.text);
          else if (e.kind === "error") appendToViper(`\n[error: ${e.message}]`);
        },
        ctrl.signal,
      );
    } catch (err) {
      appendToViper(`\n[connection error]`);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    if (runIdRef.current) void abortAssistant(token, runIdRef.current);
    setStreaming(false);
  }

  if (!open) {
    return <ViperOrb state={streaming ? "streaming" : "idle"} onClick={() => setOpen(true)} label="Open Ask Viper" />;
  }

  return (
    <section className="viper-dock glass" aria-label="Ask Viper">
      <header className="viper-dock__head">
        <ViperOrb state={streaming ? "streaming" : "idle"} label="Viper" />
        <span className="viper-dock__title">Ask Viper</span>
        <button type="button" className="viper-dock__close" onClick={() => setOpen(false)} aria-label="Collapse">
          ×
        </button>
      </header>

      <div className="viper-dock__log" role="log" aria-live="polite">
        {messages.length === 0 ? (
          <p className="viper-dock__hint">Ask about goals, lateness, or a person's month.</p>
        ) : (
          messages.map((m, i) => (
            <p key={i} className={`viper-msg viper-msg--${m.role}`}>
              <span className="viper-msg__who">{m.role}</span>
              {m.text || (m.role === "viper" && streaming ? "…" : "")}
            </p>
          ))
        )}
      </div>

      <div className="viper-dock__chips">
        {CHIPS.map((c) => (
          <button key={c} type="button" className="viper-chip" onClick={() => send(c)} disabled={streaming}>
            {c}
          </button>
        ))}
      </div>

      <form
        className="viper-dock__input"
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask…"
          aria-label="Message"
          disabled={streaming}
        />
        {streaming ? (
          <button type="button" onClick={stop}>Stop</button>
        ) : (
          <button type="submit" aria-label="Send">▶</button>
        )}
      </form>
    </section>
  );
}
```

- [ ] **Step 2: Verify the build**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/components/AssistantDock.tsx
git commit -m "feat(assistant): AssistantDock orb-to-panel chat UI"
```

---

## Task 10: Dock styles (`assistant.css`)

**Files:**
- Create: `frontend/src/styles/views/assistant.css`
- Modify: `frontend/src/styles/index.css`

- [ ] **Step 1: Create the stylesheet**

Create `frontend/src/styles/views/assistant.css`:

```css
/* Ask Viper dock — living orb -> glass panel. Reuses global tokens. */
.viper-orb {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 31;
  width: 56px;
  height: 56px;
  border: 0;
  border-radius: var(--r-pill);
  cursor: pointer;
  background: radial-gradient(circle at 35% 30%, #fff6, transparent 60%), var(--grad-sigma);
  box-shadow: var(--shadow-float);
  isolation: isolate;
}
.viper-orb__rim {
  position: absolute;
  inset: -3px;
  border-radius: inherit;
  background: conic-gradient(from 0deg, var(--s-amber), var(--s-coral), var(--s-violet), var(--s-azure), var(--s-amber));
  filter: blur(6px);
  opacity: 0.85;
  z-index: -1;
  animation: viper-rim 4.2s linear infinite;
}
.viper-orb[data-state="streaming"] .viper-orb__rim { animation-duration: 1.6s; opacity: 1; }
.viper-orb__core {
  position: absolute;
  inset: 6px;
  border-radius: inherit;
  background: var(--glass-fill);
  backdrop-filter: blur(8px);
}
@keyframes viper-rim { to { transform: rotate(360deg); } }

.viper-dock {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 30;
  display: flex;
  flex-direction: column;
  width: min(380px, calc(100vw - 32px));
  height: min(560px, calc(100vh - 48px));
  border-radius: var(--r-card);
  box-shadow: var(--shadow-float);
  overflow: hidden;
  animation: viper-pop var(--dur-smooth, 400ms) var(--spring-smooth, ease);
}
@keyframes viper-pop {
  from { transform: translateY(12px) scale(0.96); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.viper-dock__head { display: flex; align-items: center; gap: 10px; padding: 12px 14px; }
.viper-dock__head .viper-orb { position: static; width: 28px; height: 28px; box-shadow: none; }
.viper-dock__title { font-weight: 600; flex: 1; }
.viper-dock__close { border: 0; background: transparent; font-size: 20px; cursor: pointer; color: var(--label-secondary); }
.viper-dock__log { flex: 1; overflow-y: auto; padding: 8px 14px; display: flex; flex-direction: column; gap: 10px; }
.viper-dock__hint { color: var(--label-secondary); }
.viper-msg { display: flex; flex-direction: column; gap: 2px; white-space: pre-wrap; }
.viper-msg__who { font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--label-secondary); }
.viper-msg--you { align-items: flex-end; }
.viper-dock__chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px; }
.viper-chip { border: 1px solid var(--glass-highlight); background: transparent; border-radius: var(--r-pill); padding: 4px 10px; font-size: 12px; cursor: pointer; }
.viper-chip:disabled { opacity: 0.5; cursor: default; }
.viper-dock__input { display: flex; gap: 8px; padding: 12px 14px; }
.viper-dock__input input { flex: 1; border-radius: var(--r-pill); border: 1px solid var(--glass-highlight); padding: 8px 12px; background: var(--glass-fill); }
.viper-dock__input button { border: 0; border-radius: var(--r-pill); padding: 8px 14px; cursor: pointer; background: var(--grad-sigma); color: #fff; }

@media (prefers-reduced-motion: reduce) {
  .viper-orb__rim { animation: none; }
  .viper-dock { animation: none; }
}
.viper-orb[data-reduced="true"] .viper-orb__rim { animation: none; }
```

> Token names (`--grad-sigma`, `--s-amber`, `--glass-fill`, `--glass-highlight`, `--shadow-float`, `--r-card`, `--r-pill`, `--label-secondary`, `--spring-smooth`, `--dur-smooth`) are from `tokens.css`. If any differs, grep `frontend/src/styles/tokens.css` and substitute the real name.

- [ ] **Step 2: Wire it into the import chain**

Read `frontend/src/styles/index.css` and add, in the `views/*` import group:

```css
@import "./views/assistant.css";
```

- [ ] **Step 3: Verify the build**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: passes (CSS bundles).

- [ ] **Step 4: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/styles/views/assistant.css frontend/src/styles/index.css
git commit -m "feat(assistant): dock + orb styles"
```

---

## Task 11: Mount the dock for admins + managers

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Import and mount**

Read `App.tsx` and find the `AuthenticatedDashboard` component's return (it renders `<Shell …>{body}</Shell>`). Add the import near the other component imports:

```tsx
import { AssistantDock } from "./components/AssistantDock";
```

Then wrap the existing return in a fragment and render the dock as a sibling of `<Shell>`, gated on role (the role is on the `me` data the component already holds — use its actual variable, e.g. `me.data.role` or `role`):

```tsx
return (
  <>
    <Shell /* ...existing props... */>{body}</Shell>
    {["admin", "manager"].includes(role) && <AssistantDock token={token} />}
  </>
);
```

> Adapt `role` and the `<Shell>` props to the actual JSX — this is a 2-line addition (import + gated render). Do not change existing tab/Shell logic.

- [ ] **Step 2: Verify the build**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: passes.

- [ ] **Step 3: Commit**

```bash
cd ~/sigma-dashboard
git add frontend/src/App.tsx
git commit -m "feat(assistant): mount Ask Viper dock for admins + managers"
```

---

## Task 12: Enable + manual end-to-end verification

**Files:** none (ops + manual check)

- [ ] **Step 1: Configure `.env`**

Edit `~/sigma-dashboard/.env`, add (copy the token value from `~/.openclaw/openclaw.json → gateway.auth.token` — do not commit `.env`):

```
SIGMA_GATEWAY_TOKEN=<value from openclaw.json gateway.auth.token>
SIGMA_ASSISTANT_ENABLED=true
```

- [ ] **Step 2: Rebuild the frontend so the dock ships in `dist`**

Run: `cd ~/sigma-dashboard/frontend && npm run build`
Expected: passes.

- [ ] **Step 3: Restart the launchd backend**

Run: `launchctl kickstart -k gui/$(id -u)/com.sigma.dashboard`
Then: `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/`  → expect `200`.

- [ ] **Step 4: Verify in the browser**

Open http://127.0.0.1:8001/ logged in as an admin or manager (to test without the password, mint a JWT per the workspace note: `~/sigma-dashboard/.venv/bin/python -c "from backend.app.config import get_settings; from backend.app.auth import create_access_token; s=get_settings(); print(create_access_token(s, s.admin_username)[0])"` and set `localStorage['sigma-token']`).
Checks:
- The living orb appears bottom-right (rim-lights breathing).
- Click → glass panel springs open.
- Ask "say hello in one sentence" → reply streams token-by-token; orb pulses faster while streaming.
- Click **Stop** mid-stream → streaming halts.
- Log in as a `viewer` → no orb (and `POST /api/v1/assistant/chat` returns 403).

- [ ] **Step 5: Commit any tweaks from verification, then open the PR**

```bash
cd ~/sigma-dashboard
git push -u origin viper-chat
gh pr create --title "Ask Viper live chat dock" --body "Implements docs/VIPER_CHAT_PLAN.md (v2)."
```

---

## Task 13: Hand off the Viper side (no code)

- [ ] Deliver spec §9 to Viper's OpenClaw manager: for the `agent:viper:dashboard` session, ensure read-only behavior (no `send_message`/sheet-writes/`cron` when answering dashboard questions) and confirm he can answer the target questions from his db. **Reminder (spec §6): the dashboard cannot enforce this — it is entirely the manager's responsibility.** Confirm the `gateway.auth.token` matches `SIGMA_GATEWAY_TOKEN`.

---

## Self-Review

**Spec coverage:** §2 architecture → Tasks 3–4, 7–11. §3 wire format → Tasks 1, 3 (handshake, 3-part key, idempotencyKey, multiplexed `chat`, no inject, no admin scope). §4 backend (websockets dep, config+guard, sub-router, async SSE route, require_edit, abort, timeout, tests) → Tasks 1–6. §5 frontend (orb→panel dock, fetch+getReader stream, tokens, reduced-motion, admin/manager gate, private GradePill avoided) → Tasks 7–11. §6 safety (least scope, no inject, gate, isolated session, abort+timeout, flag) → Tasks 3,4,5,12. §9 Viper-side → Task 13. Decisions: admins+managers (`require_edit`) ✓; existing viper agent (session key only) ✓; minimal cost guards (idle timeout + abort, no rate-limit/budget) ✓; rely on Viper's knowledge (no context-injection task) ✓.

**Placeholder scan:** No "TBD/TODO". The few "adapt to the actual JSX/field names" notes (config validator integration, App.tsx role var, test seeding) each ship concrete code plus the exact file to mirror — the engineer always has the content; only a variable name is reconciled against existing code.

**Type consistency:** `AssistantEvent` kinds (`run`/`delta`/`final`/`error`/`aborted`) are identical across `GatewayClient.stream_chat` (Task 3), the SSE route, `streamAssistant` (Task 7), and `AssistantDock` (Task 9). `gateway_session_key`, `assistant_enabled`, `assistant_idle_timeout_s`, `get_gateway_client`, `GatewayClient`, `ViperOrb`, `AssistantDock` names match across all referencing tasks. Abort payload key `run_id` matches between `AbortRequest`, the route, and `abortAssistant`.
