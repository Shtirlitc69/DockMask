from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas import (
    AnswerBatchRequest,
    ConfigResponse,
    ConfigUpdateRequest,
    HealthResponse,
    JobCreateResponse,
    JobStatusResponse,
)

router = APIRouter()

_STORAGE: dict[str, dict[str, object]] = {}
_CONFIG_API_KEY: str | None = None


@router.post("/api/jobs", response_model=JobCreateResponse)
async def create_job(
    file: UploadFile = File(...),
    entity_types: list[str] = Form(...),
    ocr_enabled: bool = Form(False),
) -> JobCreateResponse:
    if not file.filename:
        raise HTTPException(status_code=422, detail="file is required")
    if not entity_types:
        raise HTTPException(status_code=422, detail="entity_types is required")

    job_id = str(uuid4())
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    record = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "questions": [],
        "source_filename": file.filename,
        "document_format": ext,
        "error": None,
    }
    _STORAGE[job_id] = record
    return JobCreateResponse(
        job_id=job_id,
        status=record["status"],
        source_filename=record["source_filename"],
        document_format=record["document_format"],
    )


@router.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    record = _STORAGE.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=str(record["status"]),
        progress=int(record.get("progress", 0)),
        questions=list(record.get("questions", [])),
        error=str(record["error"]) if record.get("error") else None,
    )


@router.post("/api/jobs/{job_id}/answers")
async def submit_answers(job_id: str, payload: AnswerBatchRequest) -> dict[str, object]:
    if job_id not in _STORAGE:
        raise HTTPException(status_code=404, detail="job not found")
    if not payload.answers:
        raise HTTPException(status_code=422, detail="answers cannot be empty")
    record = _STORAGE[job_id]
    record["status"] = "queued"
    record["questions"] = []
    return {"accepted": True, "job_id": job_id, "answers_count": len(payload.answers)}


@router.get("/api/config", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    return ConfigResponse(feature_flags={"ocr_enabled": False}, has_api_key=_CONFIG_API_KEY is not None)


@router.put("/api/config", response_model=ConfigResponse)
async def put_config(payload: ConfigUpdateRequest) -> ConfigResponse:
    global _CONFIG_API_KEY
    if payload.api_key is not None:
        _CONFIG_API_KEY = payload.api_key
    return ConfigResponse(feature_flags={"ocr_enabled": False}, has_api_key=_CONFIG_API_KEY is not None)


@router.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", db="ok", worker="ok")
