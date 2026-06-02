from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .bootstrap import init_db
from .config import get_settings
from .routes import router
from .schemas import Envelope, ErrorBody


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def error_response(status_code: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    envelope = Envelope(
        data=None,
        meta={},
        error=ErrorBody(code=code, message=message, details=details or {}),
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(envelope))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", "Request validation failed", {"errors": exc.errors()})

    app.include_router(router)

    dist = Path(settings.frontend_dist_path)
    if dist.exists():
        assets = dist / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")

    return app


app = create_app()
