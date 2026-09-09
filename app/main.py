from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes_jobs import router
from app.dependencies import AppServices, default_services
from app.logging_config import configure_file_logging
from app.runtime import Runtime, create_runtime
from core.config import Settings
from storage.secrets import SecretStore


def _frontend_dist() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / "frontend" / "dist"
    return Path(__file__).resolve().parents[1] / "frontend" / "dist"


def create_app(
    services: AppServices | None = None,
    settings: Settings | None = None,
    secret_store: SecretStore | None = None,
) -> FastAPI:
    runtime_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime: Runtime | None = None
        configure_file_logging(runtime_settings.logs_path)
        if services is None:
            runtime = await create_runtime(runtime_settings, secret_store=secret_store)
            application.state.services = runtime.services
        else:
            application.state.services = services
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.close()

    application = FastAPI(title="DockMask", lifespan=lifespan)
    # A TestClient that is used without its context manager does not enter the
    # lifespan. Keep the public dependency surface deterministic in that case;
    # the real runtime replaces these sentinels as soon as lifespan starts.
    application.state.services = services or default_services()

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_, __) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "request_validation_failed"})

    application.include_router(router)

    frontend_dist = _frontend_dist()
    if frontend_dist.exists():
        application.mount(
            "/",
            StaticFiles(directory=str(frontend_dist), html=True),
            name="frontend",
        )
    return application


app = create_app()


def run_server(port: int = 8000) -> None:
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    run_server()
