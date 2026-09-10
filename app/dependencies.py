"""Dependency contracts for the HTTP layer.

Concrete persistence, queue and secret-store implementations are supplied by the
application lifecycle. The defaults deliberately report unavailable services
instead of pretending that in-memory state is durable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import Request, UploadFile

from app.schemas import (
    AnswerBatchRequest,
    AnswerBatchResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigValidationRequest,
    ConfigValidationResponse,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
    ModelsRequest,
    ModelsResponse,
    PreviewResponse,
    ReportResponse,
)
from core.models import EntityType


class ServiceUnavailableError(RuntimeError):
    """A dependency is not wired yet; ``code`` is safe to expose through the API."""

    def __init__(self, code: str = "service_unavailable") -> None:
        safe_codes = {"service_unavailable", "secret_store_unavailable"}
        self.code = code if code in safe_codes else "service_unavailable"
        super().__init__(self.code)


class JobNotFoundError(LookupError):
    """The requested job does not exist."""


class JobStateError(RuntimeError):
    """The requested result is not available in the current job state."""


class PreviewUnavailableError(RuntimeError):
    """The completed artifact cannot be converted to a preview."""


class ModelDiscoveryError(RuntimeError):
    """Safe model-discovery failure exposed by the local API."""

    def __init__(self, status_code: int, code: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class JobService(Protocol):
    async def create_job(
        self,
        *,
        file: UploadFile,
        entity_types: tuple[EntityType, ...],
    ) -> JobCreateResponse: ...

    async def get_job(self, job_id: str) -> JobStatusResponse: ...

    async def cancel_job(self, job_id: str) -> JobStatusResponse: ...

    async def submit_answers(
        self,
        job_id: str,
        payload: AnswerBatchRequest,
    ) -> AnswerBatchResponse: ...

    async def get_artifact(self, job_id: str, kind: str) -> DownloadArtifact: ...

    async def get_report(self, job_id: str) -> ReportResponse: ...

    async def get_preview(self, job_id: str) -> PreviewResponse: ...


class ConfigService(Protocol):
    async def get_config(self) -> ConfigResponse: ...

    async def update_config(
        self,
        payload: ConfigUpdateRequest,
        *,
        api_key: str | None,
    ) -> ConfigResponse: ...

    async def validate_config(
        self,
        payload: ConfigValidationRequest,
        *,
        api_key: str | None,
    ) -> ConfigValidationResponse: ...

    async def list_models(self, payload: ModelsRequest, *, api_key: str | None) -> ModelsResponse: ...


class HealthService(Protocol):
    async def get_health(self) -> HealthResponse: ...


class UnavailableJobService:
    async def create_job(
        self,
        *,
        file: UploadFile,
        entity_types: tuple[EntityType, ...],
    ) -> JobCreateResponse:
        del file, entity_types
        raise ServiceUnavailableError()

    async def get_job(self, job_id: str) -> JobStatusResponse:
        del job_id
        raise ServiceUnavailableError()

    async def cancel_job(self, job_id: str) -> JobStatusResponse:
        del job_id
        raise ServiceUnavailableError()

    async def submit_answers(
        self,
        job_id: str,
        payload: AnswerBatchRequest,
    ) -> AnswerBatchResponse:
        del job_id, payload
        raise ServiceUnavailableError()

    async def get_artifact(self, job_id: str, kind: str) -> DownloadArtifact:
        del job_id, kind
        raise ServiceUnavailableError()

    async def get_report(self, job_id: str) -> ReportResponse:
        del job_id
        raise ServiceUnavailableError()

    async def get_preview(self, job_id: str) -> PreviewResponse:
        del job_id
        raise ServiceUnavailableError()


class UnavailableConfigService:
    async def get_config(self) -> ConfigResponse:
        return ConfigResponse(feature_flags={"ocr_enabled": True}, has_api_key=False)

    async def update_config(
        self,
        payload: ConfigUpdateRequest,
        *,
        api_key: str | None,
    ) -> ConfigResponse:
        del payload
        if api_key is not None:
            raise ServiceUnavailableError("secret_store_unavailable")
        return await self.get_config()

    async def validate_config(
        self,
        payload: ConfigValidationRequest,
        *,
        api_key: str | None,
    ) -> ConfigValidationResponse:
        del payload, api_key
        raise ServiceUnavailableError()

    async def list_models(self, payload: ModelsRequest, *, api_key: str | None) -> ModelsResponse:
        del payload, api_key
        raise ServiceUnavailableError()


class UnavailableHealthService:
    async def get_health(self) -> HealthResponse:
        return HealthResponse(status="degraded", db="unavailable", worker="unavailable")


@dataclass(slots=True, frozen=True)
class AppServices:
    jobs: JobService
    config: ConfigService
    health: HealthService


@dataclass(slots=True, frozen=True)
class DownloadArtifact:
    path: Path
    media_type: str
    filename: str


def default_services() -> AppServices:
    return AppServices(
        jobs=UnavailableJobService(),
        config=UnavailableConfigService(),
        health=UnavailableHealthService(),
    )


def get_services(request: Request) -> AppServices:
    services = getattr(request.app.state, "services", None)
    if services is None:
        raise ServiceUnavailableError()
    return services


def get_job_service(request: Request) -> JobService:
    return get_services(request).jobs


def get_config_service(request: Request) -> ConfigService:
    return get_services(request).config


def get_health_service(request: Request) -> HealthService:
    return get_services(request).health
