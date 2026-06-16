"""Phase 0 spike: prove the OpenClaw gateway chat path end-to-end.

Run:  cd ~/sigma-dashboard && .venv/bin/python scripts/viper_chat_spike.py "your prompt"

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
# The gateway enforces a Control-UI origin allowlist; a loopback Origin is
# accepted for local clients (auth-*.js: matchedBy "local-loopback").
ORIGIN = "http://127.0.0.1"
SESSION_KEY = "agent:viper:dashboard"
OPENCLAW_JSON = pathlib.Path.home() / ".openclaw" / "openclaw.json"
# Must be the Control-UI operator id to be granted operator.write under insecure
# local token auth (isOperatorUiClient checks id === "openclaw-control-ui").
# "webchat-ui" authenticates but is denied operator.write on chat.send.
CLIENT_ID = "openclaw-control-ui"
CLIENT_MODE = "webchat"

SAFE_DEFAULT = (
    "Dashboard health check. Reply with one short sentence confirming you can read this. "
    "Do NOT use any tools and do NOT send any messages to anyone."
)


def load_token() -> str:
    cfg = json.loads(OPENCLAW_JSON.read_text())
    return cfg["gateway"]["auth"]["token"]


async def main(prompt: str) -> None:
    token = load_token()
    async with websockets.connect(WS_URL, max_size=None,
                                   additional_headers={"Origin": ORIGIN}) as ws:
        # 1. Server pushes connect.challenge first (token auth ignores the nonce).
        first = json.loads(await ws.recv())
        assert first.get("event") == "connect.challenge", first
        # 2. Reply with the connect request.
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
                if not frame.get("ok"):
                    print("[chat.send error]", frame.get("error")); return
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
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else SAFE_DEFAULT))
