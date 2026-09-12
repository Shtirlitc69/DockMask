"""Concrete local services and the single background worker."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import UploadFile

from app.certificates import (
    CertificateStatus,
    create_gigachat_ssl_context,
    inspect_gigachat_certificate,
)
from app.dependencies import (
    AppServices,
    DownloadArtifact,
    JobNotFoundError,
    JobStateError,
    ModelDiscoveryError,
    PreviewUnavailableError,
    ServiceUnavailableError,
)
from app.schemas import (
    AnswerBatchRequest,
    AnswerBatchResponse,
    CertificateResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    ConfigValidationRequest,
    ConfigValidationResponse,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
    ModelResponse,
    ModelsRequest,
    ModelsResponse,
    PreviewResponse,
    ProviderResponse,
    QuestionResponse,
    ReplacementResponse,
    ReportResponse,
)
from core.config import Settings
from core.extractors.ocr.tesseract_provider import TesseractOcrProvider
from core.models import (
    ENTITY_DISPLAY_NAMES,
    PARTY_ROLE_DISPLAY_NAMES,
    DocumentFormat,
    EntityType,
    JobStatus,
    Location,
    Match,
    PartyRole,
)
from core.orchestrator import PipelineCancelled, run_pipeline
from core.preview import build_preview
from core.report.report_generator import format_location
from llm import (
    GigaChatScope,
    LLMClientConfig,
    ProviderId,
    get_llm_client,
    get_provider_specs,
    list_llm_models,
    validate_llm_connection,
)
from llm.http_utils import LLMHTTPError, LLMProviderError
from llm.structured import LLMResponseError
from llm.types import validate_user_base_url
from storage.db import Database
from storage.files import FileStore
from storage.jobs_repository import JobRecord, JobsRepository
from storage.secrets import KeyringSecretStore, SecretStore, SecretStoreUnavailableError

RECOMMENDED_MODELS: dict[ProviderId, list[str]] = {
    ProviderId.MOCK: ["mock"],
    ProviderId.GIGACHAT: [],
    ProviderId.OPENAI: ["gpt-4.1-mini"],
    ProviderId.ANTHROPIC: ["claude-sonnet-4-5"],
    ProviderId.OPENAI_COMPATIBLE: [],
    ProviderId.OLLAMA: ["qwen3:8b"],
    ProviderId.VLLM: [],
}
LOGGER = logging.getLogger(__name__)


def _write_csv_report(json_path: Path, csv_path: Path) -> None:
    values = json.loads(json_path.read_text(encoding="utf-8"))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=csv_path.parent,
            prefix=".report-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.writer(handle)
            writer.writerow(
                ("№", "Тип данных", "Исходный текст", "Маркер", "Роль", "Уверенность", "Расположение")
            )
            for index, item in enumerate(values, start=1):
                entity_type = EntityType(item["entity_type"])
                party_role = PartyRole(item.get("party_role", PartyRole.UNKNOWN.value))
                writer.writerow(
                    (
                        index,
                        ENTITY_DISPLAY_NAMES[entity_type],
                        item["original_value"],
                        item["replacement"],
                        PARTY_ROLE_DISPLAY_NAMES[party_role],
                        item["confidence"],
                        format_location(Location(**item.get("location", {}))),
                    )
                )
        os.replace(temporary, csv_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _serialize_matches(matches: list[Match]) -> list[dict[str, object]]:
    return [
        {
            "block_id": item.block_id,
            "entity_type": item.entity_type.value,
            "text": item.text,
            "start": item.start,
            "end": item.end,
            "replacement": item.replacement,
            "source": item.source,
            "confidence": item.confidence,
            "party_role": item.party_role.value,
            "entity_id": item.entity_id,
            "organization_id": item.organization_id,
            "evidence": [
                {
                    "kind": evidence.kind.value,
                    "block_id": evidence.block_id,
                    "subject_id": evidence.subject_id,
                    "object_id": evidence.object_id,
                    "value": evidence.value,
                    "confidence": evidence.confidence,
                }
                for evidence in item.evidence
            ],
            "conflict": item.conflict,
            "location": {
                "paragraph_index": item.location.paragraph_index,
                "table_index": item.location.table_index,
                "row": item.location.row,
                "column": item.location.column,
                "cell_paragraph_index": item.location.cell_paragraph_index,
                "sheet_name": item.location.sheet_name,
                "cell_coordinate": item.location.cell_coordinate,
                "page_number": item.location.page_number,
                "bbox": item.location.bbox,
                "ocr_words": item.location.ocr_words,
            },
        }
        for item in matches
    ]


def _deserialize_matches(values: list[dict[str, object]]) -> list[Match]:
    from core.models import EvidenceKind, EvidenceRecord

    matches: list[Match] = []
    for value in values:
        location_value = value.get("location")
        if not isinstance(location_value, dict):
            raise TypeError("invalid pending match location")
        bbox_value = location_value.get("bbox")
        words_value = location_value.get("ocr_words")
        location = Location(
            paragraph_index=location_value.get("paragraph_index"),
            table_index=location_value.get("table_index"),
            row=location_value.get("row"),
            column=location_value.get("column"),
            cell_paragraph_index=location_value.get("cell_paragraph_index"),
            sheet_name=location_value.get("sheet_name"),
            cell_coordinate=location_value.get("cell_coordinate"),
            page_number=location_value.get("page_number"),
            bbox=tuple(bbox_value) if isinstance(bbox_value, list) else bbox_value,
            ocr_words=(
                tuple(tuple(item) for item in words_value)
                if isinstance(words_value, list)
                else words_value
            ),
        )
        matches.append(
            Match(
                block_id=str(value["block_id"]),
                entity_type=EntityType(str(value["entity_type"])),
                text=str(value["text"]),
                start=int(value["start"]),
                end=int(value["end"]),
                replacement=str(value["replacement"]),
                source=str(value["source"]),
                confidence=float(value["confidence"]),
                location=location,
                party_role=PartyRole(str(value["party_role"])),
                entity_id=(str(value["entity_id"]) if value.get("entity_id") else None),
                organization_id=(
                    str(value["organization_id"]) if value.get("organization_id") else None
                ),
                evidence=tuple(
                    EvidenceRecord(
                        kind=EvidenceKind(str(item["kind"])),
                        block_id=str(item["block_id"]),
                        subject_id=str(item["subject_id"]),
                        object_id=(str(item["object_id"]) if item.get("object_id") else None),
                        value=(str(item["value"]) if item.get("value") else None),
                        confidence=float(item.get("confidence", 1.0)),
                    )
                    for item in value.get("evidence", [])
                    if isinstance(item, dict)
                ),
                conflict=bool(value.get("conflict", False)),
            )
        )
    return matches


class RuntimeConfigService:
    def __init__(
        self,
        repository: JobsRepository,
        secrets: SecretStore,
        standard_http: httpx.AsyncClient,
        gigachat_http: httpx.AsyncClient | None,
        certificate: CertificateStatus,
        *,
        development: bool,
    ) -> None:
        self._repository = repository
        self._secrets = secrets
        self._standard_http = standard_http
        self._gigachat_http = gigachat_http
        self._certificate = certificate
        self._development = development

    async def _secret(self, provider: ProviderId) -> str | None:
        try:
            return await self._secrets.get(provider.value)
        except SecretStoreUnavailableError:
            # Reads remain public and usable even when the OS credential
            # backend is temporarily unavailable. Writes still fail closed.
            return None

    def _certificate_response(self) -> CertificateResponse:
        return CertificateResponse(
            state=self._certificate.state,
            expires_at=self._certificate.expires_at,
        )

    async def get_config(self) -> ConfigResponse:
        config = await self._repository.get_config()
        provider = ProviderId(config.provider)
        secret = await self._secret(provider)
        providers = []
        for spec in get_provider_specs():
            available = not spec.development_only or self._development
            if spec.id is ProviderId.GIGACHAT:
                available = available and self._certificate.available
            providers.append(
                ProviderResponse(
                    id=spec.id,
                    display_name=spec.display_name,
                    available=available,
                    requires_base_url=spec.requires_base_url,
                    api_key_optional=not spec.requires_api_key,
                    development_only=spec.development_only,
                    recommended_models=RECOMMENDED_MODELS[spec.id],
                )
            )
        return ConfigResponse(
            feature_flags={"ocr_enabled": True},
            has_api_key=secret is not None,
            provider=provider,
            model=config.model,
            base_url=config.base_url,
            scope=config.scope,
            providers=providers,
            certificate=self._certificate_response(),
        )

    @staticmethod
    def _resolved_candidate(
        provider: ProviderId,
        model: str,
        base_url: str | None,
        api_key: str | None,
        scope: GigaChatScope | str | None = None,
    ) -> LLMClientConfig:
        normalized_base_url = base_url
        if provider is ProviderId.OPENAI_COMPATIBLE:
            if not base_url:
                raise ValueError("base_url is required")
            normalized_base_url = validate_user_base_url(base_url)
        elif provider in {ProviderId.OLLAMA, ProviderId.VLLM} and base_url:
            normalized_base_url = validate_user_base_url(base_url)
        else:
            normalized_base_url = None
        normalized_scope: str | None = None
        if provider is ProviderId.GIGACHAT:
            normalized_scope = GigaChatScope(scope or GigaChatScope.PERS).value
        return LLMClientConfig(
            provider=provider,
            model=model.strip(),
            api_key=api_key,
            base_url=normalized_base_url,
            scope=normalized_scope,
        )

    async def update_config(
        self,
        payload: ConfigUpdateRequest,
        *,
        api_key: str | None,
    ) -> ConfigResponse:
        if payload.clear_api_key and api_key:
            raise ValueError("api_key and clear_api_key are mutually exclusive")
        current = await self._repository.get_config()
        provider = payload.provider or ProviderId(current.provider)
        model = payload.model or current.model
        base_url = payload.base_url if payload.base_url is not None else current.base_url
        scope = payload.scope or (
            current.scope if ProviderId(current.provider) is provider else None
        )
        candidate = self._resolved_candidate(provider, model, base_url, None, scope)
        if not candidate.model:
            raise ValueError("model must not be empty")
        try:
            if payload.clear_api_key:
                await self._secrets.delete(provider.value)
            elif api_key and api_key.strip():
                await self._secrets.set(provider.value, api_key)
        except SecretStoreUnavailableError:
            raise ServiceUnavailableError("secret_store_unavailable") from None
        await self._repository.set_config(candidate)
        return await self.get_config()

    def _http_for(self, provider: ProviderId) -> httpx.AsyncClient | None:
        if provider is ProviderId.MOCK:
            return None
        if provider is ProviderId.GIGACHAT:
            return self._gigachat_http
        return self._standard_http

    async def resolved_config(
        self,
        config: LLMClientConfig,
        *,
        one_time_key: str | None = None,
    ) -> LLMClientConfig:
        provider = ProviderId(config.provider)
        if provider is ProviderId.GIGACHAT and not self._certificate.available:
            raise ValueError(f"certificate_{self._certificate.state}")
        secret = one_time_key or await self._secret(provider)
        return self._resolved_candidate(
            provider,
            config.model,
            config.base_url,
            secret,
            config.scope,
        )

    async def client_for(self, record: JobRecord):
        config = await self.resolved_config(
            LLMClientConfig(
                record.provider,
                record.model,
                base_url=record.base_url,
                scope=record.scope,
            )
        )
        http_client = self._http_for(ProviderId(config.provider))
        if ProviderId(config.provider) is ProviderId.GIGACHAT and http_client is None:
            raise ValueError(f"certificate_{self._certificate.state}")
        return get_llm_client(config, http_client)

    async def validate_config(
        self,
        payload: ConfigValidationRequest,
        *,
        api_key: str | None,
    ) -> ConfigValidationResponse:
        if payload.provider is ProviderId.GIGACHAT and not self._certificate.available:
            return ConfigValidationResponse(
                ok=False,
                code=f"certificate_{self._certificate.state}",
                message="GigaChat certificate is unavailable",
                certificate=self._certificate_response(),
            )
        try:
            config = await self.resolved_config(
                LLMClientConfig(
                    payload.provider,
                    payload.model,
                    base_url=payload.base_url,
                    scope=payload.scope,
                ),
                one_time_key=api_key,
            )
            result = await validate_llm_connection(config, self._http_for(payload.provider))
        except (ValueError, ServiceUnavailableError):
            return ConfigValidationResponse(
                ok=False,
                code="invalid_configuration",
                message="Invalid LLM configuration",
                certificate=self._certificate_response() if payload.provider is ProviderId.GIGACHAT else None,
            )
        return ConfigValidationResponse(
            ok=result.ok,
            code=result.code,
            message=result.message,
            certificate=self._certificate_response() if payload.provider is ProviderId.GIGACHAT else None,
        )

    async def list_models(
        self,
        payload: ModelsRequest,
        *,
        api_key: str | None,
    ) -> ModelsResponse:
        provider_id = ProviderId(payload.provider)
        if provider_id is ProviderId.GIGACHAT and not self._certificate.available:
            raise ModelDiscoveryError(422, f"certificate_{self._certificate.state}")
        current = await self._repository.get_config()
        model = current.model if ProviderId(current.provider) is provider_id else (
            RECOMMENDED_MODELS[provider_id][0] if RECOMMENDED_MODELS[provider_id] else "manual"
        )
        try:
            config = await self.resolved_config(
                LLMClientConfig(
                    provider_id,
                    model,
                    base_url=payload.base_url,
                    scope=payload.scope,
                ),
                one_time_key=api_key,
            )
            models = await list_llm_models(config, self._http_for(provider_id))
        except ValueError:
            code = (
                "gigachat_credentials_missing"
                if provider_id is ProviderId.GIGACHAT
                else "invalid_configuration"
            )
            raise ModelDiscoveryError(422, code) from None
        except LLMHTTPError as exc:
            code_by_status = {
                400: "gigachat_scope_mismatch",
                401: "gigachat_authentication_failed",
                402: "gigachat_payment_required",
                403: "gigachat_permission_denied",
                429: "gigachat_rate_limited",
            }
            code = code_by_status.get(exc.status_code, "provider_unavailable")
            status_code = exc.status_code if exc.status_code in code_by_status else 503
            raise ModelDiscoveryError(status_code, code) from None
        except LLMResponseError:
            raise ModelDiscoveryError(502, "provider_invalid_response") from None
        except (LLMProviderError, httpx.HTTPError):
            raise ModelDiscoveryError(503, "provider_unavailable") from None
        return ModelsResponse(
            models=[
                ModelResponse(
                    id=item.id,
                    display_name=item.display_name,
                    capabilities=list(item.capabilities),
                )
                for item in models
            ]
        )


class RuntimeJobService:
    def __init__(
        self,
        repository: JobsRepository,
        files: FileStore,
        queue: asyncio.Queue[str | None],
        config: RuntimeConfigService,
        cancel_events: dict[str, asyncio.Event],
    ) -> None:
        self._repository = repository
        self._files = files
        self._queue = queue
        self._config = config
        self._cancel_events = cancel_events

    async def create_job(
        self,
        *,
        file: UploadFile,
        entity_types,
    ) -> JobCreateResponse:
        job_id = str(uuid4())
        filename = file.filename or "document"
        document_format = DocumentFormat(filename.rsplit(".", 1)[-1].lower())
        source = await self._files.save_upload(job_id, file, document_format.value)
        config = await self._repository.get_config()
        await self._repository.create_job(
            job_id=job_id,
            source_filename=filename,
            document_format=document_format,
            entity_types=entity_types,
            input_path=str(source),
            config=config,
        )
        await self._queue.put(job_id)
        return JobCreateResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            source_filename=filename,
            document_format=document_format,
        )

    async def _require(self, job_id: str) -> JobRecord:
        record = await self._repository.get_job(job_id)
        if record is None:
            raise JobNotFoundError
        return record

    async def get_job(self, job_id: str) -> JobStatusResponse:
        record = await self._require(job_id)
        return JobStatusResponse(
            job_id=record.job_id,
            status=record.status,
            progress=record.progress,
            questions=[QuestionResponse.model_validate(item) for item in record.questions],
            total_replacements=record.total_replacements,
            error=record.error,
        )

    async def cancel_job(self, job_id: str) -> JobStatusResponse:
        record = await self._require(job_id)
        if record.status is JobStatus.CANCELLED:
            return await self.get_job(job_id)
        if record.status not in {
            JobStatus.QUEUED,
            JobStatus.PROCESSING,
            JobStatus.NEEDS_CLARIFICATION,
        }:
            raise JobStateError
        changed = await self._repository.set_cancelled(job_id)
        if not changed:
            current = await self._require(job_id)
            if current.status is JobStatus.CANCELLED:
                return await self.get_job(job_id)
            raise JobStateError
        event = self._cancel_events.get(job_id)
        if event is not None:
            event.set()
        else:
            await self._files.delete_job(job_id)
        return await self.get_job(job_id)

    async def submit_answers(
        self,
        job_id: str,
        payload: AnswerBatchRequest,
    ) -> AnswerBatchResponse:
        record = await self._require(job_id)
        if record.status is not JobStatus.NEEDS_CLARIFICATION:
            raise JobStateError
        expected = {str(item["question_id"]) for item in record.questions}
        provided = {item.question_id: item.answer for item in payload.answers}
        if set(provided) != expected:
            raise ValueError("answers must cover all questions")
        await self._repository.save_answers(job_id, provided)
        await self._queue.put(job_id)
        return AnswerBatchResponse(accepted=True, job_id=job_id, answers_count=len(provided))

    async def get_artifact(self, job_id: str, kind: str) -> DownloadArtifact:
        record = await self._require(job_id)
        if record.status is not JobStatus.DONE:
            raise JobStateError
        stem = Path(record.source_filename).stem
        suffix = Path(record.source_filename).suffix.lower()
        document_media_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        csv_path = (
            Path(record.json_report_path).with_suffix(".csv")
            if record.json_report_path
            else None
        )
        if kind == "csv_report" and record.json_report_path and csv_path:
            try:
                await asyncio.to_thread(
                    _write_csv_report,
                    Path(record.json_report_path),
                    csv_path,
                )
            except (OSError, ValueError, TypeError, KeyError):
                raise JobStateError from None
        mapping = {
            "document": (
                record.output_path,
                document_media_types.get(suffix, "application/octet-stream"),
                f"{stem}_обезличенный{suffix}",
            ),
            "json_report": (
                record.json_report_path,
                "application/json",
                f"{stem}_отчёт.json",
            ),
            "csv_report": (csv_path, "text/csv; charset=utf-8", f"{stem}_отчёт.csv"),
            "xlsx_report": (
                record.xlsx_report_path,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"{stem}_отчёт.xlsx",
            ),
        }
        if kind not in mapping:
            raise JobStateError
        path_value, media_type, filename = mapping[kind]
        if not path_value or not Path(path_value).is_file():
            raise JobStateError
        return DownloadArtifact(Path(path_value), media_type, filename)

    async def get_report(self, job_id: str) -> ReportResponse:
        record = await self._require(job_id)
        if record.status is not JobStatus.DONE or not record.json_report_path:
            raise JobStateError
        try:
            raw = await asyncio.to_thread(Path(record.json_report_path).read_text, encoding="utf-8")
            values = json.loads(raw)
            replacements = [ReplacementResponse.model_validate(item) for item in values]
        except (OSError, ValueError, TypeError):
            raise JobStateError from None
        return ReportResponse(total_replacements=len(replacements), replacements=replacements)

    async def get_preview(self, job_id: str) -> PreviewResponse:
        record = await self._require(job_id)
        if record.status is not JobStatus.DONE or not record.output_path:
            raise JobStateError
        report = await self.get_report(job_id)
        try:
            elements, truncated = await asyncio.to_thread(
                build_preview,
                record.output_path,
                [item.replacement for item in report.replacements],
            )
            return PreviewResponse(
                format=record.document_format,
                elements=elements,
                truncated=truncated,
            )
        except (OSError, ValueError, TypeError):
            raise PreviewUnavailableError from None


class RuntimeHealthService:
    def __init__(self, database: Database, worker: asyncio.Task[None] | None = None) -> None:
        self._database = database
        self.worker = worker

    async def get_health(self) -> HealthResponse:
        db_ok = self._database.connection is not None
        worker_ok = self.worker is not None and not self.worker.done()
        return HealthResponse(
            status="ok" if db_ok and worker_ok else "degraded",
            db="ok" if db_ok else "unavailable",
            worker="ok" if worker_ok else "unavailable",
        )


@dataclass(slots=True)
class Runtime:
    services: AppServices
    database: Database
    repository: JobsRepository
    queue: asyncio.Queue[str | None]
    worker: asyncio.Task[None]
    standard_http: httpx.AsyncClient
    gigachat_http: httpx.AsyncClient | None

    async def close(self) -> None:
        await self.queue.put(None)
        try:
            await asyncio.wait_for(self.worker, timeout=10)
        except TimeoutError:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        await self.standard_http.aclose()
        if self.gigachat_http is not None:
            await self.gigachat_http.aclose()
        await self.database.close()


async def create_runtime(
    settings: Settings,
    *,
    secret_store: SecretStore | None = None,
) -> Runtime:
    database = Database(settings.database_path)
    await database.connect()
    repository = JobsRepository(database)
    await repository.recover_interrupted()
    files = FileStore(settings.files_path)
    secrets = secret_store or KeyringSecretStore()
    certificate = inspect_gigachat_certificate()
    standard_http = httpx.AsyncClient(follow_redirects=False)
    gigachat_http = (
        httpx.AsyncClient(verify=create_gigachat_ssl_context(), follow_redirects=False)
        if certificate.available
        else None
    )
    config_service = RuntimeConfigService(
        repository,
        secrets,
        standard_http,
        gigachat_http,
        certificate,
        development=settings.env == "development",
    )
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    cancel_events: dict[str, asyncio.Event] = {}
    job_service = RuntimeJobService(repository, files, queue, config_service, cancel_events)
    health_service = RuntimeHealthService(database)
    ocr_provider = TesseractOcrProvider()

    async def worker_loop() -> None:
        while True:
            job_id = await queue.get()
            try:
                if job_id is None:
                    return
                record = await repository.get_job(job_id)
                if record is None:
                    continue
                if record.status is JobStatus.CANCELLED:
                    await files.delete_job(job_id)
                    continue
                if record.status is not JobStatus.QUEUED:
                    continue
                cancel_event = asyncio.Event()
                cancel_events[job_id] = cancel_event
                if not await repository.set_processing(job_id):
                    continue
                def check_cancelled(event: asyncio.Event = cancel_event) -> None:
                    if event.is_set():
                        raise PipelineCancelled

                try:
                    client = await config_service.client_for(record)
                    pipeline_task = asyncio.create_task(
                        run_pipeline(
                            record.input_path,
                            files.job_dir(job_id),
                            record.entity_types,
                            client,
                            answers=record.answers,
                            prepared_matches=(
                                _deserialize_matches(record.pending_matches)
                                if record.pending_matches
                                else None
                            ),
                            use_ocr=True,
                            ocr_provider=ocr_provider,
                            cancel_check=check_cancelled,
                        ),
                        name=f"dockmask-pipeline-{job_id}",
                    )
                    cancel_task = asyncio.create_task(
                        cancel_event.wait(),
                        name=f"dockmask-cancel-{job_id}",
                    )
                    try:
                        done, _ = await asyncio.wait(
                            {pipeline_task, cancel_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if cancel_task in done:
                            raise PipelineCancelled
                        result = await pipeline_task
                    finally:
                        cancel_task.cancel()
                        if not pipeline_task.done():
                            pipeline_task.cancel()
                        await asyncio.gather(
                            pipeline_task, cancel_task, return_exceptions=True
                        )
                except PipelineCancelled:
                    continue
                except (ValueError, ServiceUnavailableError):
                    current = await repository.get_job(job_id)
                    if current is not None and current.status is not JobStatus.CANCELLED:
                        await repository.set_failed(job_id, "llm_unavailable")
                    continue
                current = await repository.get_job(job_id)
                if current is None or current.status is JobStatus.CANCELLED:
                    continue
                if result.status is JobStatus.NEEDS_CLARIFICATION:
                    questions = [
                        {
                            "question_id": item.question_id,
                            "question": item.question,
                            "related_entity_type": (
                                item.related_entity_type.value if item.related_entity_type else None
                            ),
                            "options": list(item.options),
                            "context_text": item.context_text,
                            "context_location": item.context_location,
                            "highlight_start": item.highlight_start,
                            "highlight_end": item.highlight_end,
                            "contexts": list(item.contexts),
                        }
                        for item in result.open_questions
                    ]
                    await repository.set_questions(
                        job_id,
                        questions,
                        _serialize_matches(result.matches),
                    )
                elif result.status is JobStatus.DONE:
                    assert result.output_document and result.report and result.xlsx_report
                    await repository.set_result(
                        job_id,
                        output_path=result.output_document,
                        json_report_path=result.report,
                        xlsx_report_path=result.xlsx_report,
                        total_replacements=len(result.matches),
                    )
                else:
                    await repository.set_failed(job_id, result.error_message or "pipeline_failed")
            except Exception:  # noqa: BLE001 - worker must survive a failed job boundary
                if job_id is not None:
                    try:
                        current = await repository.get_job(job_id)
                        if current is not None and current.status is not JobStatus.CANCELLED:
                            await repository.set_failed(job_id, "worker_failed")
                    except Exception:  # noqa: BLE001 - health exposes a dead persistence layer
                        LOGGER.error("worker_repository_update_failed")
            finally:
                if job_id is not None:
                    cancel_events.pop(job_id, None)
                    current = await repository.get_job(job_id)
                    if current is not None and current.status is JobStatus.CANCELLED:
                        await files.delete_job(job_id)
                queue.task_done()

    worker = asyncio.create_task(worker_loop(), name="dockmask-worker")
    health_service.worker = worker
    services = AppServices(jobs=job_service, config=config_service, health=health_service)
    runtime = Runtime(
        services,
        database,
        repository,
        queue,
        worker,
        standard_http,
        gigachat_http,
    )
    for job_id in await repository.list_queued():
        await queue.put(job_id)
    return runtime
