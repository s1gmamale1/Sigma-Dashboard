"""Diagnostic: dump every gateway frame after chat.send, with per-frame timeout.

Reveals what the real stream looks like (chat vs agent events, how `final` is
signalled) so the backend GatewayClient loop terminates correctly.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import uuid

import websockets

WS_URL = "ws://127.0.0.1:18789"
ORIGIN = "http://127.0.0.1"
SESSION_KEY = "agent:viper:dashboard"
OPENCLAW_JSON = pathlib.Path.home() / ".openclaw" / "openclaw.json"
# Must be the Control-UI operator id to be granted operator.write under
# insecure local token auth (isOperatorUiClient checks id === "openclaw-control-ui").
CLIENT_ID = "openclaw-control-ui"
CLIENT_MODE = "webchat"
RECV_TIMEOUT = 90.0
MAX_FRAMES = 60


def load_token() -> str:
    return json.loads(OPENCLAW_JSON.read_text())["gateway"]["auth"]["token"]


def p(*a):
    print(*a, flush=True)


async def main(prompt: str) -> None:
    token = load_token()
    async with websockets.connect(WS_URL, max_size=None,
                                  additional_headers={"Origin": ORIGIN}) as ws:
        first = json.loads(await ws.recv())
        p("[frame] handshake-pre:", first.get("event") or first.get("type"))
        await ws.send(json.dumps({
            "type": "req", "id": "c1", "method": "connect",
            "params": {
                "minProtocol": 4, "maxProtocol": 4,
                "client": {"id": CLIENT_ID, "version": "0.0.1",
                           "platform": "backend", "mode": CLIENT_MODE},
                "role": "operator",
                "scopes": ["operator.read", "operator.write"],
                "auth": {"token": token},
            },
        }))
        hello = json.loads(await ws.recv())
        p("[hello] ok=", hello.get("ok"), "payload.type=",
          hello.get("payload", {}).get("type"), "error=", hello.get("error"))
        if not hello.get("ok"):
            return
        await ws.send(json.dumps({
            "type": "req", "id": "r1", "method": "chat.send",
            "params": {"sessionKey": SESSION_KEY, "message": prompt,
                       "idempotencyKey": str(uuid.uuid4())},
        }))
        p("[sent] chat.send to", SESSION_KEY)
        for i in range(MAX_FRAMES):
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=RECV_TIMEOUT)
            except asyncio.TimeoutError:
                p(f"[recv-timeout] no frame for {RECV_TIMEOUT}s after {i} frames")
                return
            f = json.loads(raw)
            kind = f.get("type")
            ev = f.get("event")
            pay = f.get("payload", {})
            if kind == "res":
                p(f"[{i}] res id={f.get('id')} ok={f.get('ok')} payload-keys={list(pay.keys())} runId={pay.get('runId')} err={f.get('error')}")
            elif ev == "chat":
                snippet = (pay.get("deltaText") or "")[:60]
                p(f"[{i}] event=chat state={pay.get('state')} delta={snippet!r} stop={pay.get('stopReason')} err={pay.get('errorMessage')}")
                if pay.get("state") in ("final", "error", "aborted"):
                    p("[DONE] terminal chat state:", pay.get("state"))
                    return
            else:
                # surface agent/presence/tick/health so we know what's flowing
                data = pay.get("data") if isinstance(pay, dict) else None
                p(f"[{i}] type={kind} event={ev} payload-keys={list(pay.keys()) if isinstance(pay, dict) else pay} data={str(data)[:80]}")
        p("[stop] hit MAX_FRAMES without terminal chat state")


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else (
        "Reply with exactly the word: pong. Do not use any tools.")
    asyncio.run(main(prompt))
