# Sigma Dashboard

Internal FastAPI + React dashboard for Viper-tracked attendance, reports,
goals, and project condition.

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
uvicorn backend.app.main:app --reload
```

Frontend dev server:

```bash
cd frontend
npm run dev
```

## Build

```bash
cd frontend && npm run build && cd ..
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

## API

All endpoints live under `/api/v1` and return a standard `{data, meta, error}` envelope with
two auth schemes (admin bearer JWT + the Viper `X-Viper-Token`). Interactive docs are at `/docs`
(Swagger) and `/redoc`; a quick reference with auth flow + curl examples is in
[`docs/API.md`](docs/API.md). Regenerate the OpenAPI spec (and the frontend's typed copy) with
`python scripts/export_openapi.py`.

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
SIGMA_SHEET_SYNC_HOUR=19          # 19:00 Asia/Tashkent, daily
SIGMA_SHEET_SYNC_MINUTE=0
```

Status/charge is computed from the Arrival time by the policy engine; the Status
column drives only No Show (charged) and Absent (excused). `POST /api/v1/attendance/import-sheet`
runs the same pull on demand. Run the service with a **single** worker so only one
scheduler fires (the import is idempotent regardless).
