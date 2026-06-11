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
