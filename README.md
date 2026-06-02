# Sigma Dashboard

Internal FastAPI + React dashboard for Viper-tracked attendance, reports,
goals, and project condition.

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

## Google Sheets

Set these in `.env`:

```bash
SIGMA_GOOGLE_CREDENTIALS_PATH=/absolute/path/to/google-service-account.json
SIGMA_GOOGLE_SHEET_NAME=HR Department
SIGMA_GOOGLE_SHEET_ID=
```

If `SIGMA_GOOGLE_SHEET_ID` is empty, the backend resolves the spreadsheet by
name through the Drive API. The dashboard `Sheets` tab previews tab metadata and
sample rows. `POST /api/v1/google-sheet/import` imports rows only from tabs with
recognizable canonical headers until exact tab/range coordinates are configured.
