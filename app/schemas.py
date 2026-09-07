from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobAnswer(BaseModel):
    question_id: str
    answer: str


class AnswerBatchRequest(BaseModel):
    answers: list[JobAnswer] = Field(default_factory=list)


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    source_filename: str
    document_format: str | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    questions: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class ConfigResponse(BaseModel):
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    has_api_key: bool = False


class ConfigUpdateRequest(BaseModel):
    api_key: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    db: str = "ok"
    worker: str = "ok"


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: str
