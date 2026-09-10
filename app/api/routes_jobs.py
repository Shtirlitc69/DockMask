from __future__ import annotations

import asyncio
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.dependencies import (
    ConfigService,
    HealthService,
    JobNotFoundError,
    JobService,
    JobStateError,
    ModelDiscoveryError,
    PreviewUnavailableError,
    ServiceUnavailableError,
    get_config_service,
    get_health_service,
    get_job_service,
)
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
from core.models import DocumentFormat, EntityType

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
_DOCUMENT_FORMATS = {item.value: item for item in DocumentFormat}

router = APIRouter(prefix="/api")
JobServiceDependency = Annotated[JobService, Depends(get_job_service)]
ConfigServiceDependency = Annotated[ConfigService, Depends(get_config_service)]
HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


def _api_error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=code)


def _safe_filename(filename: str | None) -> str:
    if filename is None:
        return ""
    return PurePath(filename.replace("\\", "/")).name


def _parse_entity_types(values: list[str] | None) -> tuple[EntityType, ...]:
    if not values:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "entity_types_required")

    parsed: list[EntityType] = []
    seen: set[EntityType] = set()
    try:
        for value in values:
            entity_type = EntityType(value)
            if entity_type not in seen:
                parsed.append(entity_type)
                seen.add(entity_type)
    except ValueError:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_entity_type") from None
    return tuple(parsed)


def _measure_and_rewind(file: UploadFile) -> int:
    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    return size


async def _validated_upload(
    file: UploadFile | None,
    entity_types: list[str] | None,
) -> tuple[UploadFile, tuple[EntityType, ...]]:
    if file is None:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_required")

    filename = _safe_filename(file.filename)
    if not filename:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_required")

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in _DOCUMENT_FORMATS:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "unsupported_document_format")
    size = await asyncio.to_thread(_measure_and_rewind, file)
    if size == 0:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "empty_file")
    if size > MAX_UPLOAD_SIZE_BYTES:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "file_too_large")

    file.filename = filename
    return file, _parse_entity_types(entity_types)


def _raise_service_error(exc: ServiceUnavailableError) -> None:
    raise _api_error(status.HTTP_503_SERVICE_UNAVAILABLE, exc.code) from None


@router.post("/jobs", response_model=JobCreateResponse)
async def create_job(
    service: JobServiceDependency,
    file: Annotated[UploadFile | None, File()] = None,
    entity_types: Annotated[list[str] | None, Form()] = None,
) -> JobCreateResponse:
    upload, parsed_types = await _validated_upload(file, entity_types)
    try:
        return await service.create_job(file=upload, entity_types=parsed_types)
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    service: JobServiceDependency,
) -> JobStatusResponse:
    try:
        return await service.get_job(job_id)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(job_id: str, service: JobServiceDependency) -> JobStatusResponse:
    try:
        return await service.cancel_job(job_id)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except JobStateError:
        raise _api_error(status.HTTP_409_CONFLICT, "invalid_job_state") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.post("/jobs/{job_id}/answers", response_model=AnswerBatchResponse)
async def submit_answers(
    job_id: str,
    payload: AnswerBatchRequest,
    service: JobServiceDependency,
) -> AnswerBatchResponse:
    if not payload.answers:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "answers_required")
    try:
        return await service.submit_answers(job_id, payload)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except JobStateError:
        raise _api_error(status.HTTP_409_CONFLICT, "invalid_job_state") from None
    except ValueError:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_answers") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.get("/config", response_model=ConfigResponse)
async def get_config(service: ConfigServiceDependency) -> ConfigResponse:
    try:
        return await service.get_config()
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.put("/config", response_model=ConfigResponse)
async def put_config(
    payload: ConfigUpdateRequest,
    service: ConfigServiceDependency,
) -> ConfigResponse:
    api_key = payload.api_key.get_secret_value() if payload.api_key is not None else None
    try:
        return await service.update_config(payload, api_key=api_key)
    except ValueError:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_configuration") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)
    finally:
        api_key = None


@router.post("/config/validate", response_model=ConfigValidationResponse)
async def validate_config(
    payload: ConfigValidationRequest,
    service: ConfigServiceDependency,
) -> ConfigValidationResponse:
    api_key = payload.api_key.get_secret_value() if payload.api_key is not None else None
    try:
        return await service.validate_config(payload, api_key=api_key)
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)
    finally:
        api_key = None


@router.post("/config/models", response_model=ModelsResponse)
async def config_models(
    payload: ModelsRequest,
    service: ConfigServiceDependency,
) -> ModelsResponse:
    api_key = payload.api_key.get_secret_value() if payload.api_key is not None else None
    try:
        return await service.list_models(payload, api_key=api_key)
    except ValueError:
        raise _api_error(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_configuration") from None
    except ModelDiscoveryError as exc:
        raise _api_error(exc.status_code, exc.code) from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)
    finally:
        api_key = None


async def _artifact_response(job_id: str, kind: str, service: JobService) -> FileResponse:
    try:
        artifact = await service.get_artifact(job_id, kind)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except JobStateError:
        raise _api_error(status.HTTP_409_CONFLICT, "result_not_ready") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)
    return FileResponse(
        artifact.path,
        media_type=artifact.media_type,
        filename=artifact.filename,
    )


@router.get("/jobs/{job_id}/document")
async def get_document(
    job_id: str,
    service: JobServiceDependency,
) -> FileResponse:
    return await _artifact_response(job_id, "document", service)


@router.get("/jobs/{job_id}/report", response_model=ReportResponse)
async def get_report(
    job_id: str,
    service: JobServiceDependency,
) -> ReportResponse:
    try:
        return await service.get_report(job_id)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except JobStateError:
        raise _api_error(status.HTTP_409_CONFLICT, "result_not_ready") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.get("/jobs/{job_id}/preview", response_model=PreviewResponse)
async def get_preview(
    job_id: str,
    service: JobServiceDependency,
) -> PreviewResponse:
    try:
        return await service.get_preview(job_id)
    except JobNotFoundError:
        raise _api_error(status.HTTP_404_NOT_FOUND, "job_not_found") from None
    except JobStateError:
        raise _api_error(status.HTTP_409_CONFLICT, "result_not_ready") from None
    except PreviewUnavailableError:
        raise _api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "preview_unavailable") from None
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)


@router.get("/jobs/{job_id}/report.json")
async def get_json_report(
    job_id: str,
    service: JobServiceDependency,
) -> FileResponse:
    return await _artifact_response(job_id, "json_report", service)


@router.get("/jobs/{job_id}/report.csv")
async def get_csv_report(
    job_id: str,
    service: JobServiceDependency,
) -> FileResponse:
    return await _artifact_response(job_id, "csv_report", service)


@router.get("/jobs/{job_id}/report.xlsx")
async def get_xlsx_report(
    job_id: str,
    service: JobServiceDependency,
) -> FileResponse:
    return await _artifact_response(job_id, "xlsx_report", service)


@router.get("/health", response_model=HealthResponse)
async def health(service: HealthServiceDependency) -> HealthResponse:
    try:
        return await service.get_health()
    except ServiceUnavailableError as exc:
        _raise_service_error(exc)
