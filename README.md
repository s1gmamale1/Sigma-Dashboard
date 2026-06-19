# Sigma Dashboard

Internal FastAPI + React dashboard for Viper-tracked attendance, daily reports,
performance (What/How/Why), goals, and project condition.

## Dashboard

Seven tabs (`frontend/src/App.tsx`):

- **Overview** — shift-day roll-up: tonight's attendance, weekly lateness, missing reports,
  at-risk goals, stale project topics.
- **Attendance** — tonight's roster with check-in **and check-out** times and minutes-late, a
  person × day history grid (each cell shows in/out), the weekly lateness chart, and per-record
  chase state.
- **Reports** — each person's daily report (summary, extras, 0–100 rating, missing flag).
  When the selected day has no reports yet, the tab falls back to the most recent day that does.
- **Performance** — a best→worst **What / How / Why** leaderboard over a Week / Month / Custom
  range: composite grade, rating-trend sparkline, attendance counts, punctuality, average hours,
  the latest evaluation narrative, and feedback notes.
- **Goals** — goals with owner, progress, deadline-derived status, and the latest log entry.
- **Projects** — per-topic project condition; admins can **create, edit, archive/restore, and
  delete** projects and edit titles, summaries, task checklists, and log timelines.
- **Sheets** — preview and import of the HR spreadsheet.

The team works a fixed **18:00 → 03:00** night shift (crosses midnight); attendance has five
statuses — `on_time`, `late`, `late_15`, `no_show`, `absent` — and lateness, overtime, and
average in/out times are measured as offsets from that scheduled window. There is no charge concept.

## Design

The UI follows an Apple-grade, token-driven design system — dual light/dark themes,
glass chrome (nav only), restrained spring motion, and full reduced-motion / contrast /
transparency fallbacks. Styles live in `frontend/src/styles/` (`tokens.css` · `base.css` ·
`components.css` + `views/*.css`); charts are custom SVG (no charting dependency). Full
rationale and the implementation plan are in `docs/superpowers/`.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
python -m uvicorn backend.app.main:app --reload
```

Frontend dev server:

```bash
cd frontend
npm run dev
```

## Build

```bash
cd frontend && npm run build && cd ..
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001
```

## API

All endpoints live under `/api/v1` and return a standard `{data, meta, error}` envelope with
two auth schemes (admin bearer JWT + the Viper `X-Viper-Token`). Interactive docs are at `/docs`
(Swagger) and `/redoc`; a quick reference with auth flow + curl examples is in
[`docs/API.md`](docs/API.md). Regenerate the OpenAPI spec **and** the frontend's typed copy
(`openapi.json` + `openapi.d.ts`) with `cd frontend && npm run generate:api` — running
`export_openapi.py` alone refreshes the JSON but leaves the typed `.d.ts` stale.

## Google Sheets

Set these in `.env`:

```bash
SIGMA_GOOGLE_CREDENTIALS_PATH=/absolute/path/to/google-service-account.json
SIGMA_GOOGLE_SHEET_NAME=HR Department
SIGMA_GOOGLE_SHEET_ID=
```

If `SIGMA_GOOGLE_SHEET_ID` is empty, the backend resolves the spreadsheet by
name through the Drive API (set the ID explicitly when several sheets share the
name). The dashboard `Sheets` tab previews tab metadata and sample rows.
`POST /api/v1/google-sheet/import` imports rows from generic long-format tabs.

### Attendance auto-sync

The dashboard pulls the wide HR attendance tab (`Sigma Attendnace`) so the agent
that already writes check-in/out to the sheet never double-writes:

```bash
SIGMA_GOOGLE_SHEET_ID=<the HR Department spreadsheet id>   # required when the name is ambiguous
SIGMA_ATTENDANCE_TAB=Sigma Attendnace
SIGMA_SHEET_SYNC_ENABLED=true
SIGMA_SHEET_SYNC_INTERVAL_MINUTES=10   # auto-import cadence; floored at 1 min
```

The sheet's Status column is authoritative — its five values (On time / Late / 15+ Late /
No Show / Absent) map straight to the dashboard; the Arrival time only sets the minutes-late
detail. There are no charges. `POST /api/v1/attendance/import-sheet` runs the same pull on
demand. Run the service with a **single** worker so only one scheduler fires (the import is
idempotent regardless).
