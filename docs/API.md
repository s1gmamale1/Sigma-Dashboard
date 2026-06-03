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
| `GET` | `/dashboard/overview?shift_date=` | Admin | Aggregated home view: tonight, weekly charge, missing reports, at-risk goals, stale topics. |

### Attendance
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/attendance/today?shift_date=` | Admin | Each person's record for the shift day (defaults to today). |
| `GET` | `/attendance/history?from=&to=` | Admin | People × days grid; missing days return a `missing` cell. |
| `GET` | `/attendance/weekly-summary?week_start=` | Admin | Per-person lates, charged count, total charge (UZS) for the Mon–Sun week. |
| `PATCH` | `/attendance/{record_id}/chase-state` | Admin | Set chase state (`none`/`needs_chase`/`chased`/`resolved`). |

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
| `POST` | `/viper/attendance` | Viper | Idempotent upsert of attendance (keyed on person + date); charge policy is server-side. |
| `POST` | `/viper/report` | Viper | Idempotent upsert of a daily report (keyed on person + date). |
| `POST` | `/viper/goal` | Viper | Idempotent upsert of a goal (keyed on `slug`); `progress_log` is appended. |
| `POST` | `/viper/project-condition` | Viper | Idempotent upsert of a topic's condition (keyed on `topic_id`). |

### Google Sheets
| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/sheets/sync/attendance` | Admin | Push attendance to the configured HR sheet; returns the sync run status. |
| `GET` | `/google-sheet/preview?sample_rows=` | Admin | Spreadsheet/tab metadata + sample rows to verify the wiring. |
| `POST` | `/google-sheet/import` | Admin | Import rows from tabs with recognizable headers; returns imported/skipped counts. |

## Errors

| Status | `error.code` | When |
|---|---|---|
| `401` | `HTTP_ERROR` | Missing/invalid admin bearer token or `X-Viper-Token`. |
| `403` | `HTTP_ERROR` | Valid token, wrong subject. |
| `404` | `HTTP_ERROR` | Resource not found (e.g. unknown attendance `record_id`). |
| `422` | `VALIDATION_ERROR` | Request/query validation failed; field errors in `error.details.errors`. |
| `400` | `HTTP_ERROR` | Google Sheet could not be read/imported. |
