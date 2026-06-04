# Sigma Dashboard — API Reference

The internal HTTP API behind the Sigma Dashboard: attendance, daily reports & performance,
goals, and project condition for the Viper-tracked team.

- **Base URL:** `http://<host>:8000` (FastAPI serves both the API and the built SPA)
- **Base path:** every endpoint lives under `/api/v1`
- **Interactive docs:** `/docs` (Swagger UI) · `/redoc` (ReDoc) · `/openapi.json` (raw OpenAPI 3.1)

The OpenAPI spec is the source of truth; this file is the quick reference. Regenerate the spec
**and** the frontend's typed copy with `cd frontend && npm run generate:api`
(`frontend/src/lib/openapi.json` + `openapi.d.ts`); running `export_openapi.py` alone refreshes
only the JSON and leaves the typed `.d.ts` stale.

## Response envelope

Every endpoint returns the same envelope:

```jsonc
{
  "data":  <typed payload, or null on error>,
  "meta":  { /* optional context, e.g. week_start/week_end */ },
  "error": null            // or { "code": "...", "message": "...", "details": { } }
}
```

On success `error` is `null`. On failure the HTTP status is non-2xx, `data` is `null`, and
`error` carries a machine-readable `code` + human `message`. Dates are `YYYY-MM-DD` (the shift
day, Asia/Tashkent); datetimes are ISO-8601 with offset.

## Authentication

Two schemes (both visible under **Authorize** in `/docs`):

| Scheme | Header | Used by | How to get it |
|---|---|---|---|
| **AdminBearer** (JWT) | `Authorization: Bearer <token>` | all read/admin endpoints | `POST /api/v1/auth/login`; token expires (default 8h) |
| **ViperToken** (API key) | `X-Viper-Token: <secret>` | the `/viper/*` ingest endpoints | the shared `SIGMA_VIPER_TOKEN` secret (a bearer of the same secret also works) |

```bash
# 1) Log in → grab the token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YOUR_PASSWORD"}' | jq -r .data.access_token)

# 2) Call a read endpoint
curl -s http://localhost:8000/api/v1/dashboard/overview?shift_date=2026-06-03 \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3) Viper writes a record (no login; uses the shared token)
curl -s -X POST http://localhost:8000/api/v1/viper/attendance \
  -H "X-Viper-Token: $SIGMA_VIPER_TOKEN" -H 'Content-Type: application/json' \
  -d '{"person":{"slug":"oliver","display_name":"Oliver"},
       "shift_date":"2026-06-03","check_in_at":"2026-06-03T18:02:00+05:00","status":"late"}' | jq .
```

## Endpoints

### Auth
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/auth/login` | — | Exchange admin username + password for a bearer JWT. |

### Dashboard
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/dashboard/overview?shift_date=` | Admin | Aggregated home view: tonight, weekly lateness, missing reports, at-risk goals, stale topics. |

### Attendance
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/attendance/today?shift_date=` | Admin | Each person's record for the shift day (defaults to today). |
| `GET` | `/attendance/history?from=&to=` | Admin | People × days grid; missing days return a `missing` cell. |
| `GET` | `/attendance/weekly-summary?week_start=` | Admin | Per-person counts of each status (on-time / late / 15+ late / no-show / absent) for the Mon–Sun week. |
| `PATCH` | `/attendance/{record_id}/chase-state` | Admin | Set chase state (`none`/`needs_chase`/`chased`/`resolved`). |
| `POST` | `/attendance/import-sheet` | Admin | Pull the wide HR `Sigma Attendnace` tab into the dashboard now (same job as the 19:00 auto-sync). |

Attendance records and history cells expose both `check_in_at` and `check_out_at` (the
after-midnight ~03:00 checkout, `null` until the next-day sync fills it in), alongside `status`,
`minutes_late`, `chase_state`, and `notes`.

### Reports
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/reports/daily?date=` | Admin | Each person's report for the day (summary, rating 1–4, missing flag, assignments). |

### Performance
A strict WHAT (output) / HOW (work pattern) / WHY (verdict) view per person over `[from, to]`.
`GET /performance` joins reports + attendance + the latest in-window feedback and returns a
server-computed **composite grade** (`Under`/`Average`/`Good`/`Over`, plus a 0–100 `composite_score`):

- **Output band (WHAT)** — from `average_rating`: `>=3.5` Over, `>=2.5` Good, `>=1.5` Average, else Under; no rated reports (`average_rating: null`) starts at Under.
- **Attendance penalty (HOW)** — a `no_show` drops 2 bands; `>=2` late arrivals while **not** compensating drop 1.
- **Compensation** — when someone is late but their check-outs run past the **scheduled shift end**, `compensates: true` if average overtime `>=` average lateness (only meaningful when there is lateness to offset), which **cancels** the chronic-late penalty.
- **Feedback override (WHY)** — the latest in-window feedback's `grade_adjustment` (`-1/0/+1`) shifts the final band, clamped to `[Under, Over]`.
- **Completion %** — `report_completion_rate` = non-missing reports / Mon–Sat work-days in the window.
- `avg_check_in`/`avg_check_out` are `"HH:MM"` strings (or `null` when there's no check-in/out data in the window); `avg_hours` is the mean shift length (≈9h for an 18:00 → next-day 03:xx pair), `null` when unknown. Rows are returned best→worst.

Evaluations (Viper's weekly WHAT/HOW/WHY narrative) and feedback notes (Abdul's judgment) have their
own read endpoints. `evaluation.updated_at` and `feedback.created_at` are **naive-UTC** (no `Z`).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/performance?from=&to=` | Admin | Enriched per-person rows (WHAT/HOW metrics + composite grade/score, rating trend), best-first. |
| `GET` | `/evaluations?from=&to=` | Admin | Evaluations whose period overlaps the window, newest period first (latest per person is the WHY). |
| `GET` | `/feedback?from=&to=` | Admin | Feedback notes dated within the window, newest first (the per-person timeline under WHY). |

### Goals
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/goals?status=` | Admin | All goals (owner, progress, deadline, latest log); optional `status` filter. |

### Projects
Each project carries a title, a rolling condition summary, a task checklist (`open_items` =
`[{text, done}]`), and an append-only **log timeline**. The Viper agent still writes conditions
via `/viper/project-condition`; admins additionally create/edit/archive/delete from the dashboard.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/project-conditions?include_archived=` | Admin | Each project's condition (summary, last activity, task checklist, recent logs). Active only unless `include_archived=true`. |
| `POST` | `/projects` | Admin | Create a project (`title`, optional `topic_id`/`summary`/`open_items`); `topic_id` is auto-generated when omitted. |
| `PATCH` | `/projects/{topic_id}` | Admin | Patch `title`/`summary`/`open_items`/`active`. `active:false` archives (hides from the board); `active:true` restores. |
| `DELETE` | `/projects/{topic_id}` | Admin | Permanently delete a project, its condition, and its logs (referencing goals are detached). |
| `POST` | `/projects/{topic_id}/logs` | Admin | Append a timestamped log entry and bump `last_activity_at`. |
| `DELETE` | `/projects/{topic_id}/logs/{log_id}` | Admin | Remove a single log entry. |

### Viper ingest (write API)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/viper/attendance` | Viper | Idempotent upsert of attendance (keyed on person + date); the status is derived server-side. |
| `POST` | `/viper/report` | Viper | Idempotent upsert of a daily report (keyed on person + date). |
| `POST` | `/viper/goal` | Viper | Idempotent upsert of a goal (keyed on `slug`); `progress_log` is appended. |
| `POST` | `/viper/project-condition` | Viper | Idempotent upsert of a topic's condition (keyed on `topic_id`). |
| `POST` | `/viper/evaluation` | Viper | Idempotent upsert of a weekly WHAT/HOW/WHY evaluation (keyed on person + `period_start` + `period_end`); re-posting the same period overwrites the row. |
| `POST` | `/viper/feedback` | Viper | Insert a feedback note (`note`, optional `source`, `grade_adjustment` ∈ `{-1,0,+1}`); the latest in-window note overrides a person's composite band. |

### Google Sheets
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/sheets/sync/attendance` | Admin | Push attendance to the configured HR sheet; returns the sync run status. |
| `GET` | `/google-sheet/preview?sample_rows=` | Admin | Spreadsheet/tab metadata + sample rows to verify the wiring. |
| `POST` | `/google-sheet/import` | Admin | Import rows from tabs with recognizable headers; returns imported/skipped counts. |

## Attendance auto-sync (from the HR sheet)

The Viper/openclaw agent already writes check-in/out + status into the HR Department sheet's
**`Sigma Attendnace`** tab (wide layout: col A = Date; each person occupies a 3-column block
Arrival/Out/Status from column B; names on row 2; data from row 4). The dashboard **pulls** it —
the agent does **not** double-write to the API.

- **Schedule:** every day at **19:00 Asia/Tashkent** (configurable via `SIGMA_SHEET_SYNC_HOUR`/
  `SIGMA_SHEET_SYNC_MINUTE`/`SIGMA_SHEET_SYNC_ENABLED`). At 19:00 arrivals exist; out-times (~03:00)
  appear on the following day's run.
- **Classification:** the sheet's **Status** column is authoritative — its five values map
  straight through (On time → `on_time`, Late → `late`, 15+ Late → `late_15`, No Show →
  `no_show`, Absent → `absent`); the **Arrival time** only sets the minutes-late detail. If the
  Status cell is blank, the status is derived from arrival vs the 18:00 shift (15-min grace:
  on time → `on_time`, within grace → `late`, beyond → `late_15`). There are no charges.
  Re-syncing never overwrites the admin-set **chase state** or notes.
- **Manual trigger:** `POST /api/v1/attendance/import-sheet` runs the same job on demand.
- **Config:** needs `SIGMA_GOOGLE_CREDENTIALS_PATH`, the sheet shared with the service account,
  and `SIGMA_GOOGLE_SHEET_ID` (set explicitly when several sheets share the name "HR Department").
- The older header-based `/google-sheet/import` is a separate generic importer for long-format tabs.

## Errors

| Status | `error.code` | When |
|---|---|---|
| `401` | `HTTP_ERROR` | Missing/invalid admin bearer token or `X-Viper-Token`. |
| `403` | `HTTP_ERROR` | Valid token, wrong subject. |
| `404` | `HTTP_ERROR` | Resource not found (e.g. unknown attendance `record_id`). |
| `422` | `VALIDATION_ERROR` | Request/query validation failed; field errors in `error.details.errors`. |
| `400` | `HTTP_ERROR` | Google Sheet could not be read/imported. |
