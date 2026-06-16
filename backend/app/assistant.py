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
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import require_edit
from .config import Settings, get_settings
from .models import User
from .schemas import Envelope

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
