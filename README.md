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

