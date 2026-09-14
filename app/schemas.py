from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from core.models import DocumentFormat, EntityType, JobStatus
from llm.types import GigaChatScope, ProviderId


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    related_entity_type: EntityType | None = None
    options: list[str] = Field(default_factory=list)
    context_text: str | None = None
    context_location: str | None = None
    highlight_start: int | None = Field(default=None, ge=0)
    highlight_end: int | None = Field(default=None, ge=1)
    contexts: list[dict[str, object]] = Field(default_factory=list)
    kind: Literal["party_role", "mask_decision"] = "party_role"
    reason: str | None = None


class JobAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: Literal["supplier", "buyer", "unknown", "mask", "keep"]


class AnswerBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[JobAnswer] = Field(default_factory=list)


class AnswerBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    job_id: str
    answers_count: int = Field(ge=1)


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    source_filename: str
    document_format: DocumentFormat


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    questions: list[QuestionResponse] = Field(default_factory=list)
    stages: list[dict[str, object]] = Field(default_factory=list)
    total_replacements: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$", max_length=100)


class ConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_flags: dict[str, bool] = Field(default_factory=dict)
    has_api_key: bool = False
    provider: ProviderId = ProviderId.MOCK
    model: str = "mock"
    base_url: str | None = None
    scope: GigaChatScope | None = None
    providers: list[ProviderResponse] = Field(default_factory=list)
    certificate: CertificateResponse | None = None


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None
    provider: ProviderId | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=2048)
    scope: GigaChatScope | None = None
    clear_api_key: bool = False


class ConfigValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderId
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=2048)
    scope: GigaChatScope | None = None
    api_key: SecretStr | None = None


class ConfigValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    code: str
    message: str
    certificate: CertificateResponse | None = None


class CertificateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["ready", "expiring", "expired", "missing", "integrity_failed"]
    expires_at: str | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ProviderId
    display_name: str
    available: bool
    requires_base_url: bool
    api_key_optional: bool
    development_only: bool = False
    recommended_models: list[str] = Field(default_factory=list)


class ModelsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[ModelResponse] = Field(default_factory=list)


class ModelsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderId
    base_url: str | None = Field(default=None, max_length=2048)
    scope: GigaChatScope | None = None
    api_key: SecretStr | None = None


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)


class ReplacementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    original_value: str
    replacement: str
    location: dict[str, object | None]
    source: str
    confidence: float = Field(ge=0, le=1)
    party_role: Literal["supplier", "buyer", "unknown"]
    applied: bool
    entity_id: str | None = None
    organization_id: str | None = None
    evidence: list[dict[str, object]] = Field(default_factory=list)
    conflict: bool = False


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_replacements: int = Field(ge=0)
    replacements: list[ReplacementResponse]


class PreviewSegmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    replacement: str | None = None


class PreviewLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["title", "subtitle", "label", "field", "text", "divider", "spacer"]
    segments: list[PreviewSegmentResponse] = Field(default_factory=list)


class PreviewTableCellResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segments: list[PreviewSegmentResponse] = Field(default_factory=list)


class PreviewTableResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["table"]
    rows: list[list[PreviewTableCellResponse]] = Field(default_factory=list)


class PreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: DocumentFormat
    elements: list[PreviewLineResponse | PreviewTableResponse] = Field(default_factory=list)
    truncated: bool = False


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"] = "ok"
    db: Literal["ok", "unavailable"] = "ok"
    worker: Literal["ok", "unavailable"] = "ok"


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
