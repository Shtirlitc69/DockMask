from __future__ import annotations

from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.api.routes_jobs import router
from app.dependencies import AppServices, default_services


def create_app(services: AppServices | None = None) -> FastAPI:
    application = FastAPI(title="DockMask")
    application.state.services = services or default_services()

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(_, __) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": "request_validation_failed"})

    application.include_router(router)

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
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
