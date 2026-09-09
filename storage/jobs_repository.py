"""Transactional SQLite repository for jobs and public LLM configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from core.models import DocumentFormat, EntityType, JobStatus
from llm.types import LLMClientConfig, ProviderId
from storage.db import Database


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    status: JobStatus
    source_filename: str
    document_format: DocumentFormat
    entity_types: tuple[EntityType, ...]
    input_path: str
    output_path: str | None
    json_report_path: str | None
    xlsx_report_path: str | None
    progress: int
    questions: list[dict[str, object]]
    answers: dict[str, str]
    pending_matches: list[dict[str, object]]
    total_replacements: int
    error: str | None
    provider: ProviderId
    model: str
    base_url: str | None
    scope: str | None


class JobsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create_job(
        self,
        *,
        job_id: str,
        source_filename: str,
        document_format: DocumentFormat,
        entity_types: tuple[EntityType, ...],
        input_path: str,
        config: LLMClientConfig,
    ) -> None:
        now = _now()
        connection = self._database.require_connection()
        await connection.execute(
            """INSERT INTO jobs (
                job_id, status, source_filename, document_format, entity_types,
                input_path, provider, model, base_url, scope, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                JobStatus.QUEUED.value,
                source_filename,
                document_format.value,
                json.dumps([item.value for item in entity_types]),
                input_path,
                ProviderId(config.provider).value,
                config.model,
                config.base_url,
                config.scope,
                now,
                now,
            ),
        )
        await connection.commit()

    async def get_job(self, job_id: str) -> JobRecord | None:
        cursor = await self._database.require_connection().execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return JobRecord(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            source_filename=row["source_filename"],
            document_format=DocumentFormat(row["document_format"]),
            entity_types=tuple(EntityType(value) for value in json.loads(row["entity_types"])),
            input_path=row["input_path"],
            output_path=row["output_path"],
            json_report_path=row["json_report_path"],
            xlsx_report_path=row["xlsx_report_path"],
            progress=row["progress"],
            questions=json.loads(row["questions"]),
            answers=json.loads(row["answers"]),
            pending_matches=json.loads(row["pending_matches"]),
            total_replacements=row["total_replacements"],
            error=row["error"],
            provider=ProviderId(row["provider"]),
            model=row["model"],
            base_url=row["base_url"],
            scope=row["scope"],
        )

    async def list_queued(self) -> list[str]:
        cursor = await self._database.require_connection().execute(
            "SELECT job_id FROM jobs WHERE status = ? ORDER BY created_at",
            (JobStatus.QUEUED.value,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [row["job_id"] for row in rows]

    async def _update(self, job_id: str, **values: object) -> None:
        allowed = {
            "status", "progress", "questions", "answers", "output_path",
            "json_report_path", "xlsx_report_path", "total_replacements", "error",
            "pending_matches",
        }
        if not values or not set(values) <= allowed:
            raise ValueError("invalid job update")
        encoded = {
            key: json.dumps(value, ensure_ascii=False)
            if key in {"questions", "answers", "pending_matches"}
            else value
            for key, value in values.items()
        }
        encoded["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in encoded)
        parameters = (*encoded.values(), job_id)
        connection = self._database.require_connection()
        await connection.execute(f"UPDATE jobs SET {assignments} WHERE job_id = ?", parameters)
        await connection.commit()

    async def set_processing(self, job_id: str) -> bool:
        connection = self._database.require_connection()
        cursor = await connection.execute(
            """UPDATE jobs SET status = ?, progress = 5, error = NULL, updated_at = ?
               WHERE job_id = ? AND status = ?""",
            (JobStatus.PROCESSING.value, _now(), job_id, JobStatus.QUEUED.value),
        )
        await connection.commit()
        return cursor.rowcount == 1

    async def set_questions(
        self,
        job_id: str,
        questions: list[dict[str, object]],
        pending_matches: list[dict[str, object]],
    ) -> None:
        await self._update(
            job_id,
            status=JobStatus.NEEDS_CLARIFICATION.value,
            progress=70,
            questions=questions,
            pending_matches=pending_matches,
        )

    async def save_answers(self, job_id: str, answers: dict[str, str]) -> None:
        await self._update(
            job_id,
            status=JobStatus.QUEUED.value,
            progress=0,
            answers=answers,
            questions=[],
        )

    async def set_result(
        self,
        job_id: str,
        *,
        output_path: str,
        json_report_path: str,
        xlsx_report_path: str,
        total_replacements: int,
    ) -> None:
        await self._update(
            job_id,
            status=JobStatus.DONE.value,
            progress=100,
            output_path=output_path,
            json_report_path=json_report_path,
            xlsx_report_path=xlsx_report_path,
            total_replacements=total_replacements,
            questions=[],
            pending_matches=[],
            error=None,
        )

    async def set_failed(self, job_id: str, code: str) -> None:
        await self._update(
            job_id,
            status=JobStatus.FAILED.value,
            error=code,
            progress=100,
            pending_matches=[],
        )

    async def set_cancelled(self, job_id: str) -> bool:
        connection = self._database.require_connection()
        cursor = await connection.execute(
            """UPDATE jobs SET status = ?, progress = 100, questions = '[]',
               pending_matches = '[]', error = NULL, updated_at = ?
               WHERE job_id = ? AND status IN (?, ?, ?)""",
            (
                JobStatus.CANCELLED.value,
                _now(),
                job_id,
                JobStatus.QUEUED.value,
                JobStatus.PROCESSING.value,
                JobStatus.NEEDS_CLARIFICATION.value,
            ),
        )
        await connection.commit()
        return cursor.rowcount == 1

    async def recover_interrupted(self) -> int:
        connection = self._database.require_connection()
        cursor = await connection.execute(
            """UPDATE jobs SET status = ?, error = ?, progress = 100, updated_at = ?
               WHERE status = ?""",
            (JobStatus.FAILED.value, "processing_interrupted", _now(), JobStatus.PROCESSING.value),
        )
        await connection.commit()
        return cursor.rowcount

    async def get_config(self) -> LLMClientConfig:
        cursor = await self._database.require_connection().execute(
            "SELECT provider, model, base_url, scope FROM app_config WHERE singleton = 1"
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return LLMClientConfig(ProviderId.MOCK, "mock")
        return LLMClientConfig(
            row["provider"], row["model"], base_url=row["base_url"], scope=row["scope"]
        )

    async def set_config(self, config: LLMClientConfig) -> None:
        connection = self._database.require_connection()
        await connection.execute(
            """INSERT INTO app_config(singleton, provider, model, base_url, scope, updated_at)
               VALUES (1, ?, ?, ?, ?, ?)
               ON CONFLICT(singleton) DO UPDATE SET
                 provider=excluded.provider, model=excluded.model,
                 base_url=excluded.base_url, scope=excluded.scope,
                 updated_at=excluded.updated_at""",
            (
                ProviderId(config.provider).value,
                config.model,
                config.base_url,
                config.scope,
                _now(),
            ),
        )
        await connection.commit()
