import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .attendance_sheet import import_attendance_sheet
from .bootstrap import init_db
from .config import get_settings, validate_runtime_secrets
from .db import engine
from .routes import router
from .services import UnknownPersonError
from .schemas import Envelope, ErrorBody

# Use uvicorn's logger so scheduler + sync messages appear in the normal server output.
logger = logging.getLogger("uvicorn.error")


def _run_attendance_import_once() -> str:
    settings = get_settings()
    with Session(engine) as db:
        run = import_attendance_sheet(settings, db)  # commits internally under the import lock
        logger.info("attendance sheet sync: %s — %s", run.status, run.error_message)
        return run.status


async def _attendance_sync_loop() -> None:
    """Import the attendance sheet on a fixed short interval.

    Previously this ran once per day at 19:00, so the History view could lag up to
    ~24h behind the HR sheet. Importing every ``sheet_sync_interval_minutes`` keeps
    History within minutes of the sheet. The import runs immediately on startup and
    then every interval; a sync failure is logged but never kills the loop.
    """
    settings = get_settings()
    interval_seconds = max(60.0, settings.sheet_sync_interval_minutes * 60)
    failures = 0
    while True:
        try:
            status = await asyncio.to_thread(_run_attendance_import_once)
            failures = 0 if status == "success" else failures + 1
        except Exception:  # noqa: BLE001 — never let a sync failure kill the loop
            logger.exception("attendance sheet sync failed")
            failures += 1
        # A single transient failure retries at the base interval; only *consecutive*
        # failures back off (exponentially, capped at 8x) so a persistently broken sheet
        # or credentials can't pin the Sheets API while a one-off blip stays responsive.
        await asyncio.sleep(interval_seconds * (2 ** min(max(0, failures - 1), 3)))


API_DESCRIPTION = """\
The internal API behind the **Sigma Dashboard** — attendance, daily reports &
performance, goals, and project condition for the Viper-tracked team.

### Conventions
- **Base path:** every endpoint lives under `/api/v1`.
- **Envelope:** every response is `{ "data": <payload|null>, "meta": {…}, "error": <null|{code,message,details}> }`.
  On success `error` is `null`; on failure `data` is `null` and the HTTP status is non-2xx.
- **Time:** datetimes are ISO-8601 with offset; dates are `YYYY-MM-DD` (the shift day, Asia/Tashkent).

### Authentication
Two schemes (see the **Authorize** button):
- **AdminBearer** — `POST /auth/login` returns an `access_token`; send it as
  `Authorization: Bearer <token>` on every read/admin endpoint. Tokens expire (default 8h).
- **ViperToken** — the ingest agent writes via `/viper/*` using the shared `X-Viper-Token`
  header (a bearer of the same secret also works).

### Errors
`401` missing/invalid credentials · `403` wrong subject · `404` not found ·
`422` validation (details in `error.details.errors`). All errors use the envelope above.
"""

OPENAPI_TAGS = [
    {"name": "Auth", "description": "Log in, inspect the current user, and change your own password."},
    {"name": "Users", "description": "Admin-only account management — create, edit, reset, disable, and delete users."},
    {"name": "Dashboard", "description": "Aggregated home view for a shift day."},
    {"name": "Attendance", "description": "Tonight's shift, history grid, weekly lateness summary, and chase state."},
    {"name": "Reports", "description": "Daily reports and the performance roll-up."},
    {"name": "Performance", "description": "Strict WHAT/HOW/WHY evaluation — leaderboard, composite grade, weekly evaluations, and feedback."},
    {"name": "Goals", "description": "Active goals and at-risk goals."},
    {"name": "Projects", "description": "Per-topic project condition — admin create/edit/archive/delete, task checklist, and log timeline."},
    {"name": "Viper ingest", "description": "Write API used by the Viper agent (authenticated with `X-Viper-Token`)."},
    {"name": "Google Sheets", "description": "Preview, import, and sync the HR attendance spreadsheet."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    validate_runtime_secrets(get_settings())
    init_db()
    settings = get_settings()
    task: asyncio.Task | None = None
    if settings.sheet_sync_enabled and settings.google_credentials_path:
        task = asyncio.create_task(_attendance_sync_loop())
        logger.info(
            "attendance sheet auto-sync scheduled every %d min",
            max(1, settings.sheet_sync_interval_minutes),  # report the floored cadence the loop actually uses
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


def error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    envelope = Envelope(
        data=None,
        meta={},
        error=ErrorBody(code=code, message=message, details=details or {}),
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(envelope))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        summary="Internal ops dashboard API for the Viper-tracked team.",
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        contact={"name": "Sigma Dashboard (internal)"},
        license_info={"name": "Proprietary — internal use only"},
        lifespan=lifespan,
        swagger_ui_parameters={"defaultModelsExpandDepth": 2, "displayRequestDuration": True},
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": exc.errors()})

    @app.exception_handler(UnknownPersonError)
    async def unknown_person_handler(_: Request, exc: UnknownPersonError) -> JSONResponse:
        return error_response(422, "UNKNOWN_PERSON", str(exc))

    app.include_router(router)

    from .assistant import router as assistant_router
    app.include_router(assistant_router)

    dist = Path(settings.frontend_dist_path)
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = create_app()
