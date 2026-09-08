"""High-level orchestration for extraction, detection, clarification and redaction."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable

from core.detectors.entity_detector import detect_all
from core.detectors.party_identifier import identify_parties
from core.extractors.docx_extractor import extract_docx
from core.models import (
    ClarifyingQuestion,
    DocumentFormat,
    EntityType,
    JobStatus,
    Match,
    PipelineResult,
    PartyRole,
)
from core.redaction.docx_redactor import redact_docx
from core.report.report_generator import ReportGenerator
from llm.mock_client import MockLLMClient


def _normalize_entity_types(requested_types: Iterable[EntityType | str]) -> tuple[EntityType, ...]:
    normalized: list[EntityType] = []
    seen: set[EntityType] = set()
    for value in requested_types:
        entity = value if isinstance(value, EntityType) else EntityType(str(value))
        if entity not in seen:
            seen.add(entity)
            normalized.append(entity)
    return tuple(normalized)


def _flatten_matches(matches_by_block: dict[str, list[Match]]) -> list[Match]:
    flattened: list[Match] = []
    for matches in matches_by_block.values():
        flattened.extend(matches)
    return flattened


def _role_questions(matches_by_block: dict[str, list[Match]]) -> list[ClarifyingQuestion]:
    questions: list[ClarifyingQuestion] = []
    for block_id, matches in matches_by_block.items():
        for match in matches:
            if match.entity_type not in {EntityType.ORGANIZATION, EntityType.PERSON_NAME}:
                continue
            if match.party_role is not PartyRole.UNKNOWN:
                continue
            questions.append(
                ClarifyingQuestion(
                    question=f"Укажите роль для '{match.text}' (supplier или buyer).",
                    related_entity_type=match.entity_type,
                    question_id=f"party:{block_id}:{match.start}:{match.end}",
                )
            )
    return questions


async def run_pipeline(
    file_path: str | Path,
    output_dir: str | Path,
    requested_types: Iterable[EntityType | str],
    llm_client: Any | None = None,
) -> PipelineResult:
    """Run the full document pipeline for a DOCX file.

    The source is never overwritten; redaction output and JSON report are staged in a
    dedicated directory inside ``output_dir``.
    """
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"Документ не найден: {file_path}")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    staging_dir = output_root / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)

    client = llm_client or MockLLMClient()

    try:
        extracted = await asyncio.to_thread(extract_docx, source)
        if extracted.format != DocumentFormat.DOCX:
            return PipelineResult(
                status=JobStatus.FAILED,
                error_message=f"Unsupported document format: {extracted.format}",
            )

        normalized_types = _normalize_entity_types(requested_types)
        matches_by_block = await detect_all(extracted.blocks, normalized_types, client)
        await identify_parties(extracted.blocks, matches_by_block, client)

        questions = _role_questions(matches_by_block)
        if questions:
            return PipelineResult(
                status=JobStatus.NEEDS_CLARIFICATION,
                matches=_flatten_matches(matches_by_block),
                open_questions=questions,
            )

        destination_name = f"{source.stem}.redacted.docx"
        redacted_path = staging_dir / destination_name
        await asyncio.to_thread(redact_docx, source, redacted_path, matches_by_block)

        flat_matches = _flatten_matches(matches_by_block)
        for match in flat_matches:
            match.applied = True

        report_path = staging_dir / f"{source.stem}.report.json"
        ReportGenerator.write_report(report_path, flat_matches)

        return PipelineResult(
            status=JobStatus.DONE,
            output_document=str(redacted_path),
            report=str(report_path),
            matches=flat_matches,
        )
    except Exception as exc:  # pragma: no cover - defensive guard for pipeline failures
        return PipelineResult(
            status=JobStatus.FAILED,
            error_message=str(exc),
        )


async def pipeline_run(
    file_path: str | Path,
    output_dir: str | Path,
    requested_types: Iterable[EntityType | str],
    llm_client: Any | None = None,
) -> PipelineResult:
    return await run_pipeline(file_path, output_dir, requested_types, llm_client)
