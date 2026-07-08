# Sigma Dashboard — Wishlist

> **Capture inbox for future / nice-to-have / explicitly-deferred items.** Low ceremony.
> Promote an item into [ROADMAP.md](ROADMAP.md) when it gets scoped into a phase.
>
> Buckets: **Deferred by design** (consciously out of scope) and **Future enhancements**
> (planned-later upgrades). **New ideas** is the untriaged inbox.

---

## 🚫 Deferred by design (out of scope for now)

_(consciously NOT built — each is a separate track or a non-goal, not a gap)_

---

## ✨ Future enhancements (planned-later upgrades)

_(real upgrades to build once the current system is production-grade)_

---

## 🆕 New ideas (untriaged)

_(raw ideas land here; promote to ROADMAP.md once scoped into a phase)_

---

## 🔬 Deep review findings (2026-06-12)

> Source: full-codebase review `~/.openclaw/workspace/audit-output/SIGMA_DASHBOARD_REVIEW_2026-06-12.md`
> (4-agent sweep: attendance/OFF-DAY, API contract, frontend, security/ops).

### Confirmed bugs

- ~~🐞 **[critical] P0 — stale `no_show`/`late` record survives an OFF DAY overwrite**~~ → **fixed 2026-06-12** (fix(import) 1700d00): — importer is
  upsert-only with no delete path (`backend/app/attendance_sheet.py:158-180`); "OFF DAY" cells parse to
  `None` and the row is dropped (`attendance_sheet.py:57-66,146-148`), so a previously-imported penalty
  record stays and is counted in `compute_performance_rows` (`backend/app/services.py:507,515-538,541-543`).
  Fix: detect OFF DAY in the parser and delete/overwrite the stale record. Effort: M.
- ~~🐞 **[critical] P0 — dashboard keeps going down: launchd unit never installed + port mismatch**~~ → **fixed 2026-06-12** (fix(ops) 983f3fa + live install): —
  `~/Library/LaunchAgents/com.sigma.dashboard.plist` absent; repo ships `config/com.sigma.dashboard.plist`
  binding **:8000** while the Viper client writes to **:8001** (`config/com.sigma.dashboard.plist:17`,
  `README.md:57`, `frontend/vite.config.ts:26`). Fix: canonicalize :8001, install + `launchctl load -w`,
  add `ThrottleInterval`. Effort: S.
- ~~🐞 **[high] P1 — no `off_day` status in the model**~~ → **fixed 2026-06-12** (feat(attendance) 0eb4f48 + feat(db) bbd90af): — closed 5-value set + DB CheckConstraint
  (`backend/app/models.py:9,45`; `backend/app/schemas.py:7`); adding it needs a migration; analytics must
  exclude it (`services.py:502,507,515-538,541-543`). Effort: M.
- ~~🐞 **[high] P1 — importer silently swallows "OFF DAY"**~~ → **fixed 2026-06-12** (fix(import) 1700d00): — no branch for the literal
  (`attendance_sheet.py:124-148,57-66`); indistinguishable from a blank cell. Effort: S.
- ~~🐞 **[high] P1 — whole-team Sunday OFF DAY unrecognized**~~ → **fixed 2026-06-12** (fix(import) 059717b): — "OFF DAY" in col B parses as Oliver's
  arrival and is dropped (`attendance_sheet.py:84-104`, `PERSON_BLOCK_START` `:41`); Sunday rows produce
  zero records. Fix: row-level OFF DAY detection → emit off-day rows for all four people. Effort: S.
- ~~🐞 **[high] P1 — frontend has no `off_day` rendering; StatusPill fails open**~~ → **fixed 2026-06-12** (feat(frontend) 00e9ffe): — unknown status →
  `undefined` label + unstyled class (`frontend/src/components/StatusPill.tsx:24,27`); off days surface as
  alarming "Missing" pills (`frontend/src/components/AttendanceView.tsx:91-124`); `lib/types.ts:1,32`
  lacks the status. Effort: S.
- ~~🐞 **[high] P1 — `grade` is free text, not an enum**~~ → **fixed 2026-06-12** (fix(contract) bb6245b): — `schemas.py:182`; grade bands compare
  `"Good"/"Over"/…` (`services.py:417`) so case/spelling drift silently misses the leaderboard. Fix:
  `Literal["Over","Good","Average","Under"]` + client `choices` (`scripts/dashboard_client.py:102`). Effort: S.
- ~~🐞 **[high] P1 — no server-side person allowlist**~~ → **fixed 2026-06-12** (fix(contract) 9d6e541): — `get_or_create_person` auto-creates any slug
  (`services.py:40-49`); typo spawns a phantom roster entry; allowlist only client-side
  (`dashboard_client.py:73`). Effort: S.
- ~~🐞 **[medium] P2 — goal `--owner` typo → ownerless goal, no error**~~ → **fixed 2026-06-12** (fix(contract) 9d6e541): (`services.py:140-142`). Effort: S.
- 🐞 **[medium] P2 — goal `--log` append not idempotent** — duplicate `GoalLog` rows on resend
  (`services.py:156-157`). Effort: S.
- 🐞 **[medium] P2 — dead `"excused"` branch** (`services.py:83`) not in the `AttendanceStatus` literal. Effort: S.

### Security findings

- ~~🔐 **[high] P1 — Viper token compared non-constant-time**~~ → **fixed 2026-06-12** (fix(security) 3e26d14): — `backend/app/auth.py:64` (`!=`), admin
  plaintext fallback `==` at `auth.py:25`. Fix: `secrets.compare_digest`. Effort: S.
- ~~🔐 **[high] P1 — placeholder secret defaults pass validation**~~ → **fixed 2026-06-12** (fix(security) 55fc15c): — `backend/app/config.py:12,18`
  (`"change-me-in-env"` etc. satisfy `min_length=16`); missing `.env` boots with predictable secrets.
  Fix: reject placeholder literals at startup. Effort: S.
- ~~🔐 **[high] P1 — no rate-limiting**~~ → **fixed 2026-06-12** (feat(security) 1e7e988 (login)): on `/auth/login` or `/viper/*`. Fix: slowapi limiter. Effort: M.
- 🔐 **[high] P1 — admin JWT in `localStorage`, 8h lifetime** — XSS-exfiltratable
  (`frontend/src/App.tsx:42-50`). Fix: httpOnly cookie / CSP / shorter TTL. Effort: M.
- ~~🔐 **[high] P1 — raw exception strings returned to clients**~~ → **fixed 2026-06-12** (fix(security) 40f3aba): — `backend/app/main.py:132`; also stored
  from Sheets sync (`services.py:389-397`). Fix: log server-side, generic client message. Effort: S.

### Ops / reliability

- ⚙️ **[high] P1 — no migrations** — `bootstrap.py:11` `create_all` only; `logs/dev-server.log` already
  shows `no such column: attendance_records.charged`; the `off_day` enum add will hit this. Fix: Alembic. Effort: M.
- ~~⚙️ **[high] P1 — stray empty `backend/dashboard.db` + CWD-relative `database_url`**~~ → **fixed 2026-06-12** (fixed live (.env pinned, stray removed)): — launchd
  WorkingDirectory decides which DB is used. Fix: delete stray DB; pin `SIGMA_DATABASE_URL` absolute. Effort: S.

### Tests / quality

- ~~🧪 **[medium] P2 — zero OFF DAY tests**~~ → **fixed 2026-06-12** (covered in 1700d00/059717b/239a9ed): (`backend/tests/test_attendance_sheet.py`,
  `test_attendance_policy.py`). Effort: S.
- 🧪 **[medium] P2 — auth test gaps** — `/auth/login` happy-path, wrong-password, expired-JWT; sheet
  import with malformed/OFF-DAY rows; Sheets sync error paths. Effort: M.
- 🧹 **[medium] P2 — `frontend/src/lib/openapi.d.ts` dead/unused** — drift hazard vs hand-written
  `types.ts`; delete or generate from it. Effort: S.
- 🧹 **[low] P2 — `composite_score` + `Report.assignments`/`assignment_count` fetched but never rendered**
  (`PerformanceView`/`ReportsView`). Effort: S.
- ~~🧹 **[low] P2 — pill severity ramp inverted**~~ → **fixed 2026-06-12** (feat(frontend) 00e9ffe): — `pill-absent` teal (reads positive), `pill-no_show`
  neutral grey. Effort: S.
- 🧹 **[low] P2 — unbounded text fields** (summary/what/how/why/note) — no max length. Effort: S.
- 🧹 **[low] P2 — client docstring omits `evaluation`** (`dashboard_client.py:5-6`). Effort: S.

---

## 🔬 Deep review findings (2026-06-19)

> Source: two-round xhigh workflow code review of PR #5 (attendance frequent-import,
> merged as `a4e38ff`). These three were consciously **deferred** as out-of-scope for that
> PR; none is a confirmed correctness/security bug — all are hardening/efficiency follow-ups.

### Ops / reliability

- ~~⚙️ **[medium] concurrent-import race — auto-sync loop vs on-demand endpoint**~~ → **shipped in PR #6**
  (`4d66238`, 2026-06-19): a module-level `threading.Lock` in `attendance_sheet.py` serializes the DB
  apply + commit of `import_attendance_sheet`, so the loop and the on-demand endpoint can't race the
  `(person, shift_date)` upserts; the network fetch stays outside the lock.
- ~~⚙️ **[low] immediate-import on every startup can storm the Sheets API**~~ → **shipped in PR #6**
  (`4d66238`): the auto-sync loop now applies exponential backoff (consecutive-failure only, capped 8×),
  so a persistently broken sheet/creds can't pin the Sheets API; immediate-on-boot is retained.

### Optimizations

- 🧹 **[low] Google client rebuilt every loop iteration (~144×/day)** — `import_attendance_sheet`
  → `_service()` → `build()` constructs a fresh discovery client on every run (`backend/app/google_sheets.py`).
  **Caching attempted in PR #6 and REVERTED**: an `lru_cache` on `_credentials` shared one mutable,
  non-thread-safe `Credentials` object across the (locked) import and the (un-locked) preview/dashboard-import
  endpoints — a token-refresh race — and a path-only key missed in-place key rotation. A safe win must cache
  something immutable (e.g. the parsed discovery document) or serialize *all* sheet access, not the Credentials.
  Effort: M.

### Concurrency (discovered during PR #6 review)

- ⚙️ **[medium] dashboard-import path bypasses the attendance import lock** — `import_attendance_sheet`
  is serialized by `_import_lock`, but the parallel dashboard importer
  (`routes.py` `google_sheet_import` → `google_sheets.import_google_sheet_dashboard_data` →
  `_import_attendance_rows` → `upsert_attendance`) writes the same `AttendanceRecord(person_id, shift_date)`
  unique key WITHOUT the lock. A concurrent dashboard import + auto-sync/on-demand import can still collide
  on `uq_attendance_person_shift` → `IntegrityError` (500/400 on the dashboard path, which lacks the
  never-raise handling). Fix needs a shared lock across both writers (e.g. move `_import_lock` to a neutral
  module and wrap the dashboard attendance-write section). Its own PR — touches `google_sheets.py`. Effort: M.

## 🔬 HQ control plane — deferred items (2026-06-23)

> Branch `feat/hq-control-plane` (worktree `/Users/aisigma/sigma-dashboard-hq`), unmerged/unpushed.
> From building SigmaLink-live (socket) + live blockers and the two-stage review.

### 🚫 Deferred by design (need sign-off / no live source)

- 🚫 **[actions] HQ control/write actions stay 403/501 pending Leo sign-off** — real socket tools exist
  (`stop_pane`, `close_pane`, `prompt_agent`, `send_keys`, `kill_swarm`, `create_task`) behind SigmaLink's
  supervised-autonomy authz (`free|escalate|deny` + killSwitch). Enabling control touches LIVE production
  agents → needs an explicit signed, whitelisted, escalation-aware action path + sign-off before any wiring.
  `backend/app/hq/actions.py`. Build when Leo signs off the control scope.
- 🚫 **[tasks] SigmaControl tasks/blockers have no live READ API** — only `create_task` (write);
  `get_app_state` carries no kanban. Tasks stay spec-only (UI-labeled "no live task source") until a read
  API exists. `backend/app/hq/adapters/sigmacontrol.py`.

### Optimizations / cleanups

- 🐞 **[low] SigmaLink worker dedup** — the session loop appends a Worker per agent-session with no dedup by
  id; two sessions sharing an `agentKey` produce duplicate worker entries (agentKeys unique in practice).
  `backend/app/hq/adapters/sigmalink.py` (`_snapshot_from_state` session loop). Effort: S.
- ⚙️ **[low] configurable socket timeout** — `UnixSocketTransport` timeout hardcoded 2s; promote to a setting.
  `backend/app/hq/adapters/control_socket.py`. Effort: S.
- ⚙️ **[note] real per-agent heartbeat** — live entities use `last_heartbeat=fetched_at` (liveness = "in the
  active list now"), not real activity; a hung-but-listed agent reads fresh.
  `backend/app/hq/adapters/sigmalink.py`. Effort: M.
- 🧹 **[low] file-vs-live precedence doc** — SigmaLink adapter tries the JSON state file before the live
  socket; document that file = explicit override, live = default. `backend/app/hq/adapters/sigmalink.py`
  (`fetch_snapshot`). Effort: S.
- 🧹 **[note] blocker/alert noise** — `get_app_state.notifications` includes transient/caller-induced
  tool-errors; consider filtering by kind/age/unread. The feed is app/current-view scoped, not whole-fleet.
  `backend/app/hq/adapters/sigmalink.py` (`_notifications_to_blockers`). Effort: M.

### Merge hygiene

- 🧹 **[low] squash duplicate commit** — `8b09537` + `0d7c1c6` both implement "adapter protocol + mock"
  (interruption artifact); squash at merge.

---

## 🔬 Test-coverage audit (2026-07-08)

> Source: two-agent coverage sweep (backend pytest + frontend vitest), grep-verified.
> Baseline: 126 backend tests / 20 frontend tests, all green; **no coverage tooling installed on
> either side**. Top 5 (marked ⏳) **shipped via PR #9 (squash `2942ca5`, 2026-07-08)**; the rest parked here.
> Strengths noted: `_import_lock` concurrency, composite-score engine, midnight-wraparound,
> migrations all well-tested — gaps concentrate in integration surfaces + defensive error paths.

### Tooling

- 🧪 **[medium] no coverage measurement possible** — `pytest-cov` not in `.venv`, `@vitest/coverage-v8`
  not in `frontend/package.json`. Install both + wire `--cov=backend/app` / `vitest --coverage` so future
  audits get an objective baseline instead of manual grep. Effort: S.

### Confirmed bugs (found while writing the ⏳ tests)

- 🐞 **[high] naive check-in datetime crashes the whole dashboard import** — a designator-less
  cell like `2026-06-01T18:10:00` (the natural sheet format) parses naive via
  `google_sheets._parse_datetime:274-281`, then `calculate_attendance_status` subtracts the
  **tz-aware** shift start (`services.py:107`, aware via `shift_start_datetime:85`) →
  unhandled `TypeError` → `POST /google-sheet/import` 500s (route only catches `GoogleSheetError`).
  Viper path (`+05:00` documented in schema) and HR-sheet importer (localizes to TZ) are both safe —
  only this path is exposed. Fix: localize naive parsed datetimes to `settings.timezone` in
  `_parse_datetime`. Pinned by strict-xfail `backend/tests/test_google_sheets.py::test_import_attendance_naive_checkin_datetime`
  (XPASSes when fixed → promote to a plain test). Effort: S.
- 🧹 **[low] `google_sheets._slug` doesn't collapse consecutive separators** — `"Class A / LMS"` →
  `class-a---lms`; behavior now pinned in `test_google_sheets.py::test_parse_helpers_edge_cases`.
  If ever "fixed", existing roster slugs derived from such names would shift — needs a migration
  thought, not a drive-by. Effort: S (deliberately parked).
- 🧹 **[low] dashboard importer accepts then ignores explicit `late`/`on_time`/`no_show` sheet status** —
  `_import_attendance_rows:314` validates the status vocabulary but `calculate_attendance_status:99-104`
  only honors `off_day`/`absent`; a "late" row with no check-in derives to the harsher `no_show` (−15 vs −3
  in the new composite). Either honor the explicit status or reject it loudly. Pinned in
  `test_google_sheets.py::test_import_attendance_explicit_late_without_checkin_derives_no_show`. Effort: S.

### Backend — shipped in PR #9 (⏳ → ✅ 2026-07-08)

- ⏳ 🧪 **[high] `backend/app/google_sheets.py` — entire 396-line module untested** — header-alias mapping
  (`_normalize_header:205`), multi-tab dispatch (`import_google_sheet_dashboard_data:135`), ambiguous/zero
  spreadsheet-name branches (`resolve_spreadsheet_id:52`). Effort: M.
- ⏳ 🧪 **[high] `backend/app/auth.py:82` — disabled user with valid JWT never tested** — the actual
  "disable user" enforcement point; also real-expiry + wrong-secret tokens (`auth.py:76`). Effort: S.
- ⏳ 🧪 **[high] `backend/app/services.py:349-417` — `sync_attendance_to_sheet` zero tests** — outbound
  DB→sheet push; `except Exception` → failed `SheetSyncRun` branch unexercised. Effort: M.

### Backend — parked

- 🧪 **[high] core read routes zero route-tests** — `routes.py:234` `dashboard_overview` (composes 5 calls),
  `:299` history (`end<start`→422 documented, never triggered), `:343` weekly-summary, `:388` chase-state
  (404 + persistence). Effort: M.
- 🧪 **[high] `ratelimit.py:18-28` sliding-window unit tests** — window eviction after 60s, per-key
  isolation, thread-safety under the `Lock`; only defense on `/auth/login`. Effort: S.
- 🧪 **[medium] `permissions.py` role×area matrix never asserted directly** — also: `has_permission` is
  **dead code, never called anywhere**. Assert full matrix vs `DATA_AREAS` drift. Effort: S.
- 🧪 **[medium] login with disabled account + correct password** — `routes.py:210` collapses 3 failure
  legs into one 401; the `not user.active` leg has no test. Effort: S.
- 🧪 **[medium] grace-minutes boundary at exactly 15/16 min** — `services.py:110` `<=` decides late (−3)
  vs late_15 (−5); tests only cover 10 and 25. Effort: S.
- 🧪 **[medium] `google-sheet/preview|import` route wiring** — `GoogleSheetError`→400, viewer-must-403 on
  import (`require_edit`), `sample_rows` 1..25 bounds (`routes.py:849,874`). Effort: S.
- 🧪 **[low] `routes.py:713` add-log-to-unknown-topic 404** — sibling delete endpoint has this test. Effort: S.
- 🧪 **[low] `services.parse_project_tasks:179-200` malformed/non-list JSON guards** — only thing between a
  corrupted `open_items_json` row and a 500 on every project-conditions GET. Effort: S.
- 🧪 **[low] `attendance_sheet._record_failed_run:280` double-failure fallback** — monkeypatch `db.commit`
  to raise; assert never-raises contract holds at its deepest layer. Effort: S.
- 🧪 **[low] `routes.py:622` `include_archived=true`** — restore-visibility path never exercised. Effort: S.
- 🧪 **[low] `services.require_known_person:52-65`** — display-name-drift update + empty-string skip. Effort: S.
- 🧪 **[low] `main.py:96-113` lifespan gating** — auto-sync task created only for
  `(sheet_sync_enabled AND creds_path)`; flip to `or` = crash loop nothing catches. Effort: S.

### Frontend — shipped in PR #9 (⏳ → ✅ 2026-07-08)

- ⏳ 🧪 **[high] `frontend/src/lib/dates.ts:52` `parseServerDate` untested** — the fix for the shipped
  naive-UTC bug; a "simplify to `new Date`" refactor regresses silently (UTC+5 shift). Effort: S.
- ⏳ 🧪 **[high] `frontend/src/lib/api.ts:66-82` `apiFetchEnvelope` error branches** — non-OK status,
  200-with-error envelope, non-JSON body; every API call funnels through it. Effort: S.

### Frontend — parked

- 🧪 **[high] `App.tsx:84-119` permission tabs + expired-token logout** — viewer must never see Users tab;
  failed `/me` must clear token + bounce to login (else infinite spinner); `needsFallback` date substitution.
  Needs first `QueryClientProvider` test wrapper — build `test/renderWithQueryClient.tsx` helper. Effort: M.
- 🧪 **[high] `AttendanceView.tsx:23-42` optimistic chase-state rollback** — the app's only optimistic
  mutation; failed PATCH must roll back or UI silently desyncs from backend. Effort: M.
- 🧪 **[medium] `lib/api.ts:191-229` `streamAssistant` SSE parsing** — frame split across two `read()`
  chunks, malformed-frame silent catch, non-OK initial response. Effort: S.
- 🧪 **[medium] `LoginPanel.tsx:14-26` failure path** — error message shown + button re-enabled via
  `finally`; regression = permanent lockout with no feedback. Effort: S.
- 🧪 **[medium] `UsersView.tsx:130-196` destructive guards** — self-delete `disabled={isSelf}` +
  `window.confirm` gate. Effort: S.
- 🧪 **[medium] `AssistantDock.tsx:184-231` send/stop** — `/compress`→`/compact` alias, empty-message guard,
  `stop()` aborts + `abortAssistant(runId)`; existing test only covers markdown rendering. Effort: M.
- 🧪 **[medium] `ProjectEditor.tsx:79-201` unsaved-changes confirm + archive toggle direction**. Effort: S.
- 🧪 **[low] `lib/dates.ts:8-34` `addDays`/`weekStart`/`monthRange` boundaries** — month/year rollover,
  Sunday→preceding-Monday, February range. Effort: S.
- 🧪 **[low] `ChangePasswordPanel.tsx:20-30` client validation** — length<6 + mismatch guards on the
  forced-change path every new user hits. Effort: S.
- 🧪 **[low] `PerformanceView.tsx:71-80` evaluation tie-break + rank stability under "Worst first"**. Effort: S.
- 🧪 **[low] `Shell.tsx:60-70` date-stepper wiring** — prev/next/today → `onDate` args. Effort: S.
- 🧪 **[low] `SheetsView.tsx:58-79` preview-error + import-result states**. Effort: S.
- 🧪 **[low] `Sparkline.tsx:29-45` NaN/empty/single-point clamping** — NaN in SVG path renders nothing,
  throws nothing. Effort: S.
- 🧪 **[low] `ProjectConditionView.tsx:15-25` `relativeTime` buckets + null/NaN guards**. Effort: S.
- 🧪 **[low] `Avatar.tsx` empty-name → `"?"` not crash; `StatusPill.tsx:23-29` unknown-enum fallback**. Effort: S.
