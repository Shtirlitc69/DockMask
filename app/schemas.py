from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from core.models import DocumentFormat, EntityType, JobStatus


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question: str
    related_entity_type: EntityType | None = None


class JobAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    answer: str


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
    total_replacements: int = Field(default=0, ge=0)
    error: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$", max_length=100)


class ConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_flags: dict[str, bool] = Field(default_factory=dict)
    has_api_key: bool = False


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"] = "ok"
    db: Literal["ok", "unavailable"] = "ok"
    worker: Literal["ok", "unavailable"] = "ok"


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
