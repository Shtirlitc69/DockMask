from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.dependencies import AppServices, JobNotFoundError, ServiceUnavailableError
from app.main import create_app
from app.schemas import (
    AnswerBatchRequest,
    AnswerBatchResponse,
    ConfigResponse,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
)
from core.models import DocumentFormat, EntityType, JobStatus


@dataclass
class FakeJobService:
    jobs: dict[str, JobStatusResponse] = field(default_factory=dict)
    received_types: tuple[EntityType, ...] = ()
    received_ocr: bool | None = None
    received_content: bytes = b""

    async def create_job(
        self,
        *,
        file: UploadFile,
        entity_types: tuple[EntityType, ...],
        ocr_enabled: bool,
    ) -> JobCreateResponse:
        self.received_types = entity_types
        self.received_ocr = ocr_enabled
        self.received_content = await file.read()
        suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
        job_id = "job-1"
        response = JobCreateResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            source_filename=file.filename or "",
            document_format=DocumentFormat(suffix),
        )
        self.jobs[job_id] = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            progress=0,
            total_replacements=0,
        )
        return response

    async def get_job(self, job_id: str) -> JobStatusResponse:
        try:
            return self.jobs[job_id]
        except KeyError:
            raise JobNotFoundError from None

    async def submit_answers(
        self,
        job_id: str,
        payload: AnswerBatchRequest,
    ) -> AnswerBatchResponse:
        if job_id not in self.jobs:
            raise JobNotFoundError
        return AnswerBatchResponse(
            accepted=True,
            job_id=job_id,
            answers_count=len(payload.answers),
        )


@dataclass
class FakeConfigService:
    stored_api_key: str | None = None

    async def get_config(self) -> ConfigResponse:
        return ConfigResponse(
            feature_flags={"ocr_enabled": False},
            has_api_key=self.stored_api_key is not None,
        )

    async def update_config(self, *, api_key: str | None) -> ConfigResponse:
        if api_key is not None:
            self.stored_api_key = api_key
        return await self.get_config()


@dataclass
class FakeHealthService:
    response: HealthResponse = field(default_factory=HealthResponse)

    async def get_health(self) -> HealthResponse:
        return self.response


def _client() -> tuple[TestClient, FakeJobService, FakeConfigService]:
    jobs = FakeJobService()
    config = FakeConfigService()
    services = AppServices(jobs=jobs, config=config, health=FakeHealthService())
    return TestClient(create_app(services)), jobs, config


@pytest.mark.parametrize("extension", ["docx", "pdf", "xlsx"])
def test_create_job_accepts_supported_formats(extension: str) -> None:
    client, jobs, _ = _client()

    response = client.post(
        "/api/jobs",
        files={"file": (f"document.{extension}", b"document", "application/octet-stream")},
        data={"entity_types": ["inn", "phone", "inn"]},
    )

    assert response.status_code == 200
    assert response.json() == {
        "job_id": "job-1",
        "status": "queued",
        "source_filename": f"document.{extension}",
        "document_format": extension,
    }
    assert jobs.received_types == (EntityType.INN, EntityType.PHONE)
    assert jobs.received_ocr is False
    assert jobs.received_content == b"document"


@pytest.mark.parametrize(
    ("files", "data", "expected_code"),
    [
        (None, {"entity_types": "inn"}, "file_required"),
        ({"file": ("", b"document")}, {"entity_types": "inn"}, "request_validation_failed"),
        ({"file": ("document.txt", b"document")}, {"entity_types": "inn"}, "unsupported_document_format"),
        ({"file": ("document.docx", b"")}, {"entity_types": "inn"}, "empty_file"),
        ({"file": ("document.docx", b"document")}, {}, "entity_types_required"),
        ({"file": ("document.docx", b"document")}, {"entity_types": "unknown"}, "invalid_entity_type"),
        (
            {"file": ("document.docx", b"document")},
            {"entity_types": "inn", "ocr_enabled": "true"},
            "ocr_not_available",
        ),
    ],
)
def test_create_job_returns_safe_validation_codes(
    files: dict[str, tuple[str, bytes]] | None,
    data: dict[str, str],
    expected_code: str,
) -> None:
    client, _, _ = _client()

    response = client.post("/api/jobs", files=files, data=data)

    assert response.status_code == 422
    assert response.json() == {"detail": expected_code}


def test_create_job_enforces_size_limit_and_rewinds_upload() -> None:
    client, jobs, _ = _client()

    with patch("app.api.routes_jobs.MAX_UPLOAD_SIZE_BYTES", 4):
        response = client.post(
            "/api/jobs",
            files={"file": ("document.docx", b"12345")},
            data={"entity_types": "inn"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "file_too_large"}
    assert jobs.received_content == b""


def test_job_status_and_not_found() -> None:
    client, _, _ = _client()
    client.post(
        "/api/jobs",
        files={"file": ("document.docx", b"document")},
        data={"entity_types": "inn"},
    )

    response = client.get("/api/jobs/job-1")
    missing = client.get("/api/jobs/missing")

    assert response.status_code == 200
    assert response.json()["total_replacements"] == 0
    assert missing.status_code == 404
    assert missing.json() == {"detail": "job_not_found"}


def test_existing_answers_route_uses_injected_service() -> None:
    client, _, _ = _client()
    client.post(
        "/api/jobs",
        files={"file": ("document.docx", b"document")},
        data={"entity_types": "inn"},
    )

    response = client.post(
        "/api/jobs/job-1/answers",
        json={"answers": [{"question_id": "question-1", "answer": "supplier"}]},
    )
    empty = client.post("/api/jobs/job-1/answers", json={"answers": []})

    assert response.status_code == 200
    assert response.json() == {"accepted": True, "job_id": "job-1", "answers_count": 1}
    assert empty.status_code == 422
    assert empty.json() == {"detail": "answers_required"}


def test_config_key_is_write_only(caplog: pytest.LogCaptureFixture) -> None:
    client, _, config = _client()
    secret = "never-return-this-key"

    updated = client.put("/api/config", json={"api_key": secret})
    fetched = client.get("/api/config")

    assert updated.status_code == 200
    assert fetched.status_code == 200
    assert updated.json() == {"feature_flags": {"ocr_enabled": False}, "has_api_key": True}
    assert fetched.json() == updated.json()
    assert secret not in updated.text
    assert secret not in fetched.text
    assert "api_key" not in updated.json()
    assert config.stored_api_key == secret
    assert secret not in caplog.text


def test_service_error_rejects_untrusted_detail() -> None:
    secret = "external-response-with-secret"

    error = ServiceUnavailableError(secret)

    assert error.code == "service_unavailable"
    assert secret not in str(error)


def test_default_services_are_explicitly_unavailable() -> None:
    client = TestClient(create_app())
    secret = "never-return-this-key"

    create = client.post(
        "/api/jobs",
        files={"file": ("document.docx", b"document")},
        data={"entity_types": "inn"},
    )
    config = client.put("/api/config", json={"api_key": secret})
    health = client.get("/api/health")

    assert create.status_code == 503
    assert create.json() == {"detail": "service_unavailable"}
    assert config.status_code == 503
    assert config.json() == {"detail": "secret_store_unavailable"}
    assert secret not in config.text
    assert health.status_code == 200
    assert health.json() == {
        "status": "degraded",
        "db": "unavailable",
        "worker": "unavailable",
    }


def test_injected_health_service_reports_ready() -> None:
    client, _, _ = _client()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "worker": "ok"}
