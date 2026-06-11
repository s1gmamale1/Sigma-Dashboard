# Review-Fixes Design — OFF DAY, Ops Bring-up, P1 Hardening (2026-06-12)

Source: verified findings from `~/.openclaw/workspace/audit-output/SIGMA_DASHBOARD_REVIEW_2026-06-12.md`
(all P0/P1 items re-verified against code and the live system on 2026-06-12; see WISHLIST.md
"Deep review findings"). Three refinements found during verification:

1. The OFF DAY P0 is **latent** — live DB has zero `no_show`/`absent`/Sunday rows today, so no
   data is corrupted yet. The path is real and bites on the first OFF declared after an import.
2. Port **:8000 is owned by a different launchd app** (`com.aisigma.netsbuilder`, PID 2437).
   The shipped plist would port-conflict. **:8001 is mandatory**, not just recommended. The
   dashboard currently runs unmanaged on :8001 (manual `uvicorn`, PID 53705).
3. The Viper client (`dashboard_client.py`) lives in `~/projects/SigmasDashboard/scripts/`,
   not in this repo — the grade-enum fix spans both repos.

## Scope

Three work packages, in the review's recommended order:

- **WP1 — Ops bring-up (P0):** canonicalize :8001, install launchd unit, pin the DB path.
- **WP2 — OFF DAY end-to-end (P0/P1):** model → migration → importer → analytics → frontend → tests.
- **WP3 — P1 hardening:** grade enum, person allowlist, constant-time token compare,
  placeholder-secret rejection, error sanitization, minimal login rate-limit.

Deferred (stay on WISHLIST.md): Alembic adoption, JWT→httpOnly-cookie move, openapi.d.ts
dead file, composite-score/assignments rendering, goal-log idempotency, unbounded text caps,
report-completion denominator for weekday off days, broader auth test gaps.

## Decisions

### D1 — OFF DAY is a first-class `off_day` status (chosen over alternatives)

- **A (chosen): add `off_day` to the status set.** Visible in the UI ("Off" pill, not a scary
  "Missing"), distinguishable from "no data imported", and the importer fix becomes a plain
  idempotent upsert that overwrites stale records.
- B (rejected): delete the record when OFF DAY appears. Kills the P0 but loses information —
  an off day renders identically to a never-imported day, and admin `chase_state`/`notes` vanish.
- C (rejected): separate day-off calendar table. Joins in every analytics path; overkill for one flag.

`ATTENDANCE_STATUSES` gains `"off_day"` (`models.py:9`), `AttendanceStatus` Literal gains it
(`schemas.py:7`), `calculate_attendance_status` returns `("off_day", 0)` for an explicit
`off_day` (covers Viper direct upserts too).

### D2 — Importer semantics: OFF DAY upserts (overwrites stale), never drops

In `_upsert_row`/`classify_sheet_row` (`attendance_sheet.py`): a cell is an off day when the
arrival text normalizes to `"off day"` **or** the status text does. Result: upsert the record
with `status="off_day"`, `check_in_at/check_out_at=None`, `minutes_late=0`, preserving
admin-owned `chase_state`/`notes`. This single change closes the P0: a stale `no_show`/`late`
row for that (person, date) is overwritten, not silently kept.

### D3 — Whole-team Sunday row

In `parse_attendance_grid`: if the **first block's arrival cell** is OFF DAY and every other
block in the row is blank (Viper writes "OFF DAY" into col B and clears C..M), emit an
off-day `SheetAttendanceRow` for **every** person block, not just the first. Per-person OFF
DAY cells continue through the normal block path (D2).

### D4 — Analytics exclusion

`compute_performance_rows` (`services.py`): filter `off_day` records out of the attendance
record set before counts/punctuality/penalties/in-out/hours (one filter line; the loops then
need no other change). Weekly summary (`routes.py:314`) already ignores unknown statuses via
its fixed counts dict — `off_day` is automatically excluded from late/no-show counts and the
lateness BarChart, which reads those counts. History grid returns the real `off_day` cell.

### D5 — Migration: targeted SQLite rebuild at bootstrap (Alembic deferred)

No Alembic exists and SQLite cannot ALTER a CHECK constraint. `bootstrap.init_db` gains an
idempotent pre-`create_all` step: inspect `sqlite_master` DDL for `attendance_records`; if the
CHECK lacks `off_day`, rebuild (create-new → copy → drop → rename) inside one transaction.
Runs once, no-ops thereafter. Full Alembic adoption stays a wishlist track.

### D6 — Canonical port :8001 everywhere + launchd install

- `config/com.sigma.dashboard.plist`: port → **8001**, add `ThrottleInterval` 10. Keep
  `KeepAlive`/`RunAtLoad`; `.venv/bin/uvicorn` verified present.
- `frontend/vite.config.ts:26` proxy → `127.0.0.1:8001` (currently proxies to the *wrong app*).
- `README.md` port references → 8001.
- Live `.env`: pin `SIGMA_DATABASE_URL=sqlite:////Users/aisigma/sigma-dashboard/dashboard.db`
  (absolute) so the CWD can never select the wrong DB. Delete stray empty `backend/dashboard.db`.
- Install: copy plist → `~/Library/LaunchAgents/`, kill the manual uvicorn (PID 53705),
  `launchctl load -w`, verify via `launchctl list` + HTTP health probe on :8001.

### D7 — Grade enum (cross-repo)

`ViperEvaluationUpsert.grade` → `Literal["Over", "Good", "Average", "Under"]` (`schemas.py:182`),
matching `GRADE_BANDS` (`services.py:417`). Client `--grade` gains
`choices=["Over", "Good", "Average", "Under"]` (`~/projects/SigmasDashboard/scripts/dashboard_client.py:102`).
Existing DB rows are unaffected (column stays String).

### D8 — Server-side person allowlist for Viper writes

New `require_known_person(db, slug)` → 422 on a slug not present in `people`. Applied to Viper
report / evaluation / feedback upserts **and** goal `owner_slug` (closes the silent
owner-typo P2 as a side effect). The sheet importer keeps `get_or_create_person` — the sheet
name row is the roster source of truth. Display-name refresh behavior unchanged.

### D9 — Constant-time secret comparison

`auth.py:64` and `auth.py:25` → `secrets.compare_digest` on UTF-8 bytes.

### D10 — Reject placeholder secrets at startup

App lifespan startup: if `jwt_secret` or `viper_token` starts with `change-me` → raise
RuntimeError with a clear message. Tests that construct `Settings` explicitly are unaffected;
test fixtures will be checked and given real-looking values if they rely on defaults.

### D11 — Error-detail sanitization

`routes.py:599, 806, 827` stop returning `str(exc)`; log the exception server-side, return a
generic message ("sheet sync failed — see server logs"). `SheetSyncRun.error_message` keeps
the detail — it is only surfaced on admin-authenticated endpoints and is the ops debugging
trail.

### D12 — Minimal login rate-limit (no new dependency)

In-app fixed-window limiter on `POST /auth/login` only: per-client-IP, 5 attempts / 60 s,
in-memory dict, 429 on breach. Viper endpoints are token-authed on a LAN bind — out of scope.
(slowapi adoption parked on the wishlist if multi-process ever matters; launchd runs one process.)

### D13 — StatusPill hardening + severity colors

`StatusPill`: add `off_day: "Off"` label; defensive `labels[value] ?? value` fallback (never a
blank pill again). CSS: `pill-off_day` calm neutral; fix the inverted ramp — `pill-absent`
loses its positive teal, `pill-no_show` becomes alarming. `lib/types.ts` `Status` gains
`"off_day"`.

## Testing

- **Importer:** per-person OFF DAY cell → `off_day` record; OFF DAY overwrites a pre-existing
  `no_show` for the same (person, date) — the P0 regression test; whole-team Sunday row →
  4 off-day records; blank cell still drops.
- **Analytics:** person with off_day records → punctuality/penalty/avg-hours identical to the
  same person without those records.
- **Migration:** old-DDL database gains `off_day` capability after bootstrap; running twice no-ops.
- **Hardening:** grade enum 422s a lowercase grade; unknown person slug 422s; placeholder
  secret aborts startup; login limiter 429s the 6th attempt; existing suite stays green.
- **Ops (manual):** `launchctl list` shows the unit; `kill` the process → relaunched within
  ~10 s; health endpoint answers on :8001.

## Rollout order

WP1 (service up, correct port/DB) → WP2 (OFF DAY) → WP3 (hardening) — matching the review's
recommended order; each WP lands as its own commit(s) with the suite green.
