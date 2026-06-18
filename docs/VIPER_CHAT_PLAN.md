# Viper Live Chat in the Sigma Dashboard — Implementation Plan (v2, recon-verified)

**Goal:** an in-dashboard chat with **Viper** for internal **analytics, quick chat, and Q&A**
("who's at risk this week?", "summarize Aiden's month", "what's blocking the promo video?"),
answered from Viper's own knowledge of his workflow + db — **safely** (no group spam, no data
mutation, no secret leakage) and **efficiently** (reuse the existing gateway, no per-message cold
starts).

> **v2 note.** This revision replaces the original paraphrased protocol with the *actual* OpenClaw
> gateway wire format (reverse-engineered from `/opt/homebrew/lib/node_modules/openclaw/dist/`), and
> reflects four product decisions taken 2026-06-16. Items the recon **corrected** are flagged ⚠️.

---

## 0. Ownership split (decided 2026-06-16)

This feature has two sides. They are built and owned separately.

| Side | Owner | Scope |
|---|---|---|
| **Platform side** | this repo (dashboard) | Backend gateway-proxy + SSE endpoint + the "Ask Viper" dock. Connects to the **existing `viper` agent**. |
| **Viper side** | Viper's OpenClaw manager | Viper's persona, tools, read-only behavior, and his knowledge of the dashboard/db. Configured on the OpenClaw side (see §9 checklist). |

We use the **existing `viper` agent** (not a new restricted clone) because he already knows the
workflow and the website. The dashboard makes the conversation *possible*; his manager makes it
*safe and knowledgeable*.

**Decisions:**
1. **Access:** admins **+ managers** (`require_edit`). Managers will see performance scores; no
   redaction in this scope (flagged, not blocked).
2. **Read-only:** enforced on **Viper's side** by his manager — see the §6 caveat (the dashboard
   *cannot* technically enforce it).
3. **Cost:** not a concern right now — no spend budgeting. Keep only abort + a run timeout (for UX
   and robustness, not cost).
4. **Grounding:** rely on Viper's own knowledge of his db/workflow. No context-injection or
   dashboard-API-as-tool work in this scope (optional future, §8).

---

## 1. Why not `openclaw -p`
`openclaw -p` is a headless **one-shot**: a fresh CLI process per message → cold-start latency,
no token streaming, awkward session continuity. Wrong tool for a live widget. We reuse the
already-running gateway's chat control plane instead.

## 2. Architecture

```
AssistantDock (React, glass orb → panel, admins+managers)
   │  POST /api/v1/assistant/chat   (Authorization: Bearer <JWT>)   ← SSE stream out
   │  POST /api/v1/assistant/abort
   ▼
FastAPI backend ── backend/app/assistant.py  (new sub-router)
   │  • holds gateway token (never sent to browser); loaded from .env
   │  • opens client WS to the gateway, performs the connect handshake (role=operator)
   │  • chat.send → session "agent:viper:dashboard"; relays `chat` deltas back as SSE
   ▼
OpenClaw gateway  ws://127.0.0.1:18789   (auth.mode=token, loopback, protocol v4)
   ▼
EXISTING viper agent  →  isolated "dashboard" session (own thread)
```

Everything is **loopback on the Mac mini**. Remote dashboard access (Tailscale) only tunnels
browser→backend; backend→gateway stays on 127.0.0.1.

⚠️ **Two gateways exist — do not confuse them.** The macOS desktop app talks to a *Python
tui_gateway* (JSON-RPC 2.0, `message.delta`/`message.complete`). We connect to the **OpenClaw
Node gateway on :18789**, which uses a different frame format (`{type:"req"|"res"|"event"}`).
Never reuse the desktop client's `JsonRpcGatewayClient`.

## 3. The real gateway protocol (verified against source)

Sources: `server-ws-runtime-*.js`, `message-handler-*.js`, `src-*.js`, `chat-*.js`,
`session-key-*.js` under `/opt/homebrew/lib/node_modules/openclaw/dist/`.

**Handshake** ⚠️ *(direction is reversed vs the original draft):*
1. On TCP accept the **server** pushes `{type:"event", event:"connect.challenge", payload:{nonce, ts}}`.
2. The **client** replies with the first `connect` request. For **token auth the nonce is unused**
   (it only matters for device-signature auth).

```jsonc
// client → server (first client frame)
{ "type":"req", "id":"c1", "method":"connect", "params":{
    "minProtocol":4, "maxProtocol":4,
    "client":{ "id":"<valid-id>", "version":"1.0.0", "platform":"backend", "mode":"backend" },
    "role":"operator",
    "scopes":["operator.read","operator.write"],     // NOT operator.admin
    "auth":{ "token":"<gateway token — server-side only>" } } }
// server → res payload {type:"hello-ok", protocol:4, features, snapshot, auth, policy}
```

**Send a turn:**
```jsonc
{ "type":"req", "id":"r2", "method":"chat.send", "params":{
    "sessionKey":"agent:viper:dashboard",            // ⚠️ THREE parts, "agent:" prefix required
    "message":"who's at risk this week?",
    "idempotencyKey":"<uuid per request>" } }          // ⚠️ REQUIRED (NonEmptyString)
// immediate res payload: { runId, status:"started" }
```

**Streaming back** ⚠️ *(one multiplexed `chat` event, switch on `payload.state`):*
```jsonc
{ "type":"event", "event":"chat", "payload":{ "runId", "sessionKey", "seq",
    "state":"delta",   "deltaText":"…", "replace":false } }   // 0..N
{ "type":"event", "event":"chat", "payload":{ "state":"final",  "stopReason", "usage" } } // exactly 1
{ "type":"event", "event":"chat", "payload":{ "state":"error",  "errorKind", "errorMessage" } }
{ "type":"event", "event":"chat", "payload":{ "state":"aborted", "stopReason":"client_abort" } }
```
There are **no** separate `chat.delta`/`chat.final` events. (`agent`/`presence`/`tick`/`health`
events also stream; we ignore them for chat.)

**Abort:**
```jsonc
{ "type":"req", "id":"r4", "method":"chat.abort",
  "params":{ "sessionKey":"agent:viper:dashboard", "runId":"<runId>" } }
```

**Dropped:** `chat.inject` — requires `operator.admin` **and** an already-open session. We don't
need it; if we ever want to prime context, prepend it to the `chat.send` `message` body instead.

**Protocol gotchas to honor in code:**
- All frames are `additionalProperties:false` (TypeBox-validated) — send no extra fields.
- Server pings every **25 s**; the `websockets` Python lib auto-`pong`s (don't disable it).
- `client.id` must be a valid enum value; `client.mode` ∈ {webchat, cli, ui, backend, node, probe, test}.
- Session `agent:viper:dashboard` is created **on first `chat.send`** — no pre-declaration.

## 4. Backend changes (`/Users/aisigma/sigma-dashboard/backend/app/`)

- ⚠️ **New dependency:** add `websockets` to `requirements.txt` (neither `websockets` nor
  `aiohttp` is currently a usable client lib — `httpx` has no WS, `uvicorn[standard]`'s
  `websockets` is server-side only).
- **`config.py`** — add `SIGMA_`-prefixed settings: `gateway_ws_url="ws://127.0.0.1:18789"`,
  `gateway_token`, `gateway_agent="viper"`, `gateway_session="dashboard"`,
  `assistant_enabled=false`, `assistant_run_timeout_s`. ⚠️ If `gateway_token` gets a placeholder
  default, add it to the `bad` list in `validate_runtime_secrets()` so the app won't boot insecure.
- **`assistant.py` (new sub-router)** — establishes the first sub-router (`APIRouter(prefix="/api/v1")`,
  included in `main.py` alongside the existing router; keeps the ~1130-line `routes.py` from growing).
  Contains `GatewayWSClient`: `await` connect.challenge → send `connect` → `stream_chat(prompt,
  session) -> AsyncIterator[event]` issuing `chat.send` and yielding normalized deltas; plus
  `abort(run_id)`. Uses `websockets`.
- **Routes** (both `Depends(require_edit)` — admins + managers):
  - `POST /api/v1/assistant/chat` → ⚠️ the app's **first `async def` route**, returns a
    `StreamingResponse(media_type="text/event-stream")` of `data: {...}\n\n` deltas. Server-side
    run timeout; map gateway `error`/`aborted` states to terminal SSE frames.
  - `POST /api/v1/assistant/abort` → cancels the in-flight run via `chat.abort`.
  - (`GET /api/v1/assistant/history` optional — via `chat.history`; defer unless needed.)
- **Light guard only** (cost is not a concern): a generous per-user send cap is *optional*. The
  hardcoded `ratelimit.py` (5/60, keyed on IP) can't be reused as-is for a per-user chat cap — if
  we add one, it's a small separate keyed limiter. Skip for v1 per the cost decision.
- **Tests** (`backend/tests/test_assistant.py`) — follow the existing pattern: in-memory SQLite +
  `app.dependency_overrides[get_db]`, real admin/manager JWT via `create_access_token()`. Mock the
  gateway WS. Assert: auth gating (viewer→403), SSE framing, delta→final flow, abort, timeout.
  Reading the stream needs `client.stream(...)` (a new test idiom here). Then `npm run generate:api`.
- **CORS:** none today (frontend served same-origin from `dist`). Only needed if a dev server hits
  the SSE endpoint cross-port — add `CORSMiddleware` then.

## 5. Frontend changes (`/Users/aisigma/sigma-dashboard/frontend/src/`)

- **Surface — "Ask Viper" living-orb dock** (chosen form factor). A `.sigma-orb` pinned
  bottom-right (`z-index:30`, above the `z-index:20` topbar); click springs it open
  (`--spring-smooth`/`--dur-smooth`) into a corner **glass** panel (`.glass`, `--r-card`,
  `--shadow-float`); collapses back to the orb. Mount in `AuthenticatedDashboard` as a sibling of
  `<Shell>`, rendered only when `["admin","manager"].includes(me.role)`. No portal infra exists —
  render inline (or add `createPortal(…, document.body)`).
- **Orb behavior (sigma-designs):** 4 independent rim-lights (mixed ω, periods 2.8–4.6 s) breathing
  while idle; pulse/eruption envelope (sharp attack, soft decay) while Viper streams. Honor
  `prefers-reduced-motion` via the existing `useReducedMotion` hook (freeze orb, drop entry anim).
- **`lib/api.ts`** — add `streamAssistant(token, prompt, onDelta, signal)` using **`fetch` + a
  `ReadableStream` reader** (⚠️ `EventSource` can't send the `Authorization` header). Parse
  `data: …` SSE lines, dispatch deltas. `abortAssistant()` via `apiFetchEnvelope`. Token is read
  from `localStorage["sigma-token"]` and passed down as a prop (no Context exists today).
- **`components/AssistantDock.tsx` (new)** — streamed message list, input, **Stop** button (wired to
  abort + `AbortController`), reduced-motion-safe typing indicator, suggested-prompt chips
  ("at-risk goals", "this week's lateness", "Aiden's month"). Reuse `Card`, `EmptyState`,
  `StatusPill`. Wrap the stream in a TanStack `useMutation` (`mutateAsync` gives `isPending`).
  ⚠️ `GradePill` is private to `PerformanceView` — extract it if reused.
- **Tokens to reuse:** `.glass`, `--glass-fill`, `--shadow-float`, `--r-card`/`--r-pill`,
  `--grad-sigma`/`--s-violet`/`--s-azure`, `--spring-smooth`/`--spring-snappy`. Dock styles live in
  a new `styles/views/assistant.css` added to the `index.css` @import chain.
- **Markdown rendering (shipped, PR #4).** Viper replies render through `react-markdown` +
  `remark-gfm` (GFM tables, lists, code, headings, blockquotes, links) — previously they showed raw
  text (`**bold**` literal, pipe-tables as plain rows). **User messages stay literal** (never
  reparsed). XSS-safe by construction: no `rehype-raw` (raw HTML in markdown is escaped, not
  executed), `react-markdown@9` sanitizes URLs by default, links get `rel="noopener noreferrer"`.
  Tables are wrapped (`.viper-md__table-wrap`) for horizontal scroll + a sticky header so they don't
  overflow the 380px dock. Styling reuses the design tokens above.

## 6. Safety model (corrected)

⚠️ **The original "deny tools on the session" guarantee is not real for live chat.** OpenClaw has
**no per-session tool deny-list** for interactive sessions (only cron jobs get `enabled_toolsets`;
a referenced upstream "tool filtering" PR was never merged). So the dashboard **cannot** prevent
Viper from using `send_message`/sheet-writes/`cron` — that enforcement lives **entirely on Viper's
side** (his manager, §9).

**What the dashboard *does* control (defense-in-depth):**
1. **Token never reaches the browser** — lives in `.env`, loaded server-side from
   `openclaw.json → gateway.auth.token`; only FastAPI talks to the gateway.
2. **Least privilege on the wire** — connect with `operator.read`+`operator.write` only (no
   `operator.admin`); never call `chat.inject`.
3. **Access gate** — `require_edit` (admins + managers).
4. **Isolated session** — `agent:viper:dashboard` is its own thread (verified free + isolated); it
   won't pollute or interleave with the attendance/report/cron sessions.
5. **Abort + timeout** — Stop button → `chat.abort`; server-side run timeout; cap output length.
6. **Feature flag** — `SIGMA_ASSISTANT_ENABLED=false` until ready.
7. **No new public surface** — same `/api/v1`, envelope, auth, port.

## 7. Phases (each independently shippable)

| Phase | Scope | Owner |
|---|---|---|
| **0 — Spike** | standalone script: connect.challenge → `connect` → `chat.send` to `agent:viper:dashboard` → print streamed `chat` deltas. Proves token + handshake + session + protocol. No UI. | dashboard |
| **1 — Backend** | `websockets` dep + `assistant.py` sub-router (`GatewayWSClient`, SSE chat route, abort) + config + flag + tests. `require_edit`. | dashboard |
| **2 — Frontend** | `AssistantDock` (orb→panel) + `streamAssistant` + `assistant.css` + admins/managers gate. | dashboard |
| **V — Viper's side** | read-only persona + confirm dashboard-data knowledge (parallel, independent). | Viper's manager |

## 8. Optional future (not in scope now)
If Viper's own knowledge proves insufficient for *exact* live metrics: give the dashboard read-API
as a callable tool (he already holds a `VIPER_TOKEN` for `:8001`) or inject the current
overview/performance JSON into the `chat.send` body. Deferred per the grounding decision.

## 9. Viper-side setup checklist (for his manager)
Because read-only can't be enforced from the dashboard, his manager must ensure, for the
`agent:viper:dashboard` session/persona:
- **No outbound spam / mutation when answering dashboard questions** — must not call `send_message`
  (Telegram group), sheet writes (via `terminal`), or `cron` edits in this context. Enforce via
  persona/`IDENTITY.md`/`SOUL.md`, or by routing dashboard traffic to a read-only-configured agent.
- **Knows the data** — confirm Viper can answer from his db/records for the target questions
  (at-risk, lateness, per-person month summaries).
- Confirm the gateway token in `openclaw.json → gateway.auth.token` is the one mirrored into the
  dashboard `.env` (`SIGMA_GATEWAY_TOKEN`).

## 10. Out of scope / explicitly NOT doing
- No browser→gateway direct connection (token stays server-side).
- No new network port or public exposure.
- No `chat.inject`, no `operator.admin` scope.
- The dashboard chat does **not** itself post to Telegram or write to the sheet/DB (Viper's tool
  governance is his manager's responsibility).
- No score redaction for managers in this scope (flagged).
- No per-message cost budgeting.
