# Sigma Dashboard — API Reference

The internal HTTP API behind the Sigma Dashboard: attendance, daily reports & performance,
goals, and project condition for the Viper-tracked team.

- **Base URL:** `http://<host>:8000` (FastAPI serves both the API and the built SPA)
- **Base path:** every endpoint lives under `/api/v1`
- **Interactive docs:** `/docs` (Swagger UI) · `/redoc` (ReDoc) · `/openapi.json` (raw OpenAPI 3.1)

The OpenAPI spec is the source of truth; this file is the quick reference. Regenerate the spec
(and the frontend's typed copy) with `python scripts/export_openapi.py` →
`frontend/src/lib/openapi.json`.

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

### Reports
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/reports/daily?date=` | Admin | Each person's report for the day (summary, rating 1–4, missing flag, assignments). |
| `GET` | `/performance?from=&to=` | Admin | Per-person roll-up (avg rating, completion %, missing days), best-first. |

### Goals
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/goals?status=` | Admin | All goals (owner, progress, deadline, latest log); optional `status` filter. |

### Projects
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/project-conditions` | Admin | Rolling condition per active topic (summary, last activity, open items). |

### Viper ingest (write API)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/viper/attendance` | Viper | Idempotent upsert of attendance (keyed on person + date); the status is derived server-side. |
| `POST` | `/viper/report` | Viper | Idempotent upsert of a daily report (keyed on person + date). |
| `POST` | `/viper/goal` | Viper | Idempotent upsert of a goal (keyed on `slug`); `progress_log` is appended. |
| `POST` | `/viper/project-condition` | Viper | Idempotent upsert of a topic's condition (keyed on `topic_id`). |

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
