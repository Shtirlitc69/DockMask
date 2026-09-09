"""Lightweight coordinator for extraction, analysis, clarification and redaction."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

from core.detectors.entity_detector import detect_all
from core.detectors.party_identifier import identify_parties
from core.extractors.docx_extractor import extract_docx
from core.extractors.pdf_extractor import extract_pdf
from core.extractors.xlsx_extractor import extract_xlsx
from core.models import (
    ClarifyingQuestion,
    DocumentFormat,
    EntityType,
    JobStatus,
    Match,
    PartyRole,
    PipelineResult,
)
from core.redaction.docx_redactor import redact_docx
from core.redaction.pdf_redactor import redact_pdf
from core.redaction.xlsx_redactor import redact_xlsx
from core.report.report_generator import ReportGenerator, generate_report
from llm.base import BaseLLMClient

_EXTRACTORS = {
    DocumentFormat.DOCX: extract_docx,
    DocumentFormat.XLSX: extract_xlsx,
    DocumentFormat.PDF: extract_pdf,
}
_REDACTORS = {
    DocumentFormat.DOCX: redact_docx,
    DocumentFormat.XLSX: redact_xlsx,
    DocumentFormat.PDF: redact_pdf,
}


def _normalize_entity_types(requested_types: Iterable[EntityType | str]) -> tuple[EntityType, ...]:
    normalized: list[EntityType] = []
    for value in requested_types:
        entity = value if isinstance(value, EntityType) else EntityType(str(value))
        if entity not in normalized:
            normalized.append(entity)
    return tuple(normalized)


def _flatten_matches(matches_by_block: Mapping[str, Iterable[Match]]) -> list[Match]:
    return [match for matches in matches_by_block.values() for match in matches]


def _question_id(match: Match) -> str:
    return f"party:{match.block_id}:{match.start}:{match.end}"


def _apply_answers(
    matches_by_block: Mapping[str, Iterable[Match]],
    answers: Mapping[str, str],
) -> set[str]:
    accepted: set[str] = set()
    for match in _flatten_matches(matches_by_block):
        question_id = _question_id(match)
        value = answers.get(question_id)
        if value not in {item.value for item in PartyRole}:
            continue
        match.party_role = PartyRole(value)
        accepted.add(question_id)
    return accepted


def _role_questions(
    matches_by_block: Mapping[str, Iterable[Match]],
    answered: set[str],
) -> list[ClarifyingQuestion]:
    questions: list[ClarifyingQuestion] = []
    for match in _flatten_matches(matches_by_block):
        if match.entity_type not in {EntityType.ORGANIZATION, EntityType.PERSON_NAME}:
            continue
        question_id = _question_id(match)
        if match.party_role is not PartyRole.UNKNOWN or question_id in answered:
            continue
        questions.append(
            ClarifyingQuestion(
                question=f"Укажите роль найденной стороны для замены {match.replacement}.",
                related_entity_type=match.entity_type,
                question_id=question_id,
                options=tuple(item.value for item in PartyRole),
            )
        )
    return questions


async def run_pipeline(
    file_path: str | Path,
    output_dir: str | Path,
    requested_types: Iterable[EntityType | str],
    llm_client: BaseLLMClient | None = None,
    *,
    answers: Mapping[str, str] | None = None,
    prepared_matches: Iterable[Match] | None = None,
    use_ocr: bool = False,
) -> PipelineResult:
    """Process a DOCX, XLSX or text PDF and atomically publish its outputs."""

    source = Path(file_path)
    if not source.is_file():
        raise FileNotFoundError("input document was not found")
    if llm_client is None:
        raise ValueError("llm_client must be provided by the application factory")
    try:
        document_format = DocumentFormat(source.suffix.lower().lstrip("."))
        normalized_types = _normalize_entity_types(requested_types)
    except ValueError:
        return PipelineResult(status=JobStatus.FAILED, error_message="invalid_configuration")
    if not normalized_types:
        return PipelineResult(status=JobStatus.FAILED, error_message="entity_types_required")

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=output_root))
    try:
        extracted = await asyncio.to_thread(_EXTRACTORS[document_format], source)
        if extracted.is_scanned:
            code = "ocr_not_available" if use_ocr else "ocr_required"
            return PipelineResult(status=JobStatus.FAILED, error_message=code)

        if prepared_matches is None:
            matches_by_block = await detect_all(extracted.blocks, normalized_types, llm_client)
            await identify_parties(extracted.blocks, matches_by_block, llm_client)
        else:
            matches_by_block: dict[str, list[Match]] = {}
            for match in prepared_matches:
                matches_by_block.setdefault(match.block_id, []).append(match)
        answered = _apply_answers(matches_by_block, answers or {})
        questions = _role_questions(matches_by_block, answered)
        if questions:
            return PipelineResult(
                status=JobStatus.NEEDS_CLARIFICATION,
                matches=_flatten_matches(matches_by_block),
                open_questions=questions,
            )

        staged_document = staging / f"{source.stem}.redacted{source.suffix.lower()}"
        await asyncio.to_thread(
            _REDACTORS[document_format],
            source,
            staged_document,
            matches_by_block,
        )
        flat_matches = _flatten_matches(matches_by_block)
        staged_json = staging / f"{source.stem}.report.json"
        staged_xlsx = staging / f"{source.stem}.report.xlsx"
        await asyncio.to_thread(
            ReportGenerator.write_report,
            staged_json,
            flat_matches,
            applied_only=True,
        )
        await asyncio.to_thread(generate_report, matches_by_block, staged_xlsx)

        final_document = output_root / staged_document.name
        final_json = output_root / staged_json.name
        final_xlsx = output_root / staged_xlsx.name
        for staged_path, final_path in (
            (staged_document, final_document),
            (staged_json, final_json),
            (staged_xlsx, final_xlsx),
        ):
            staged_path.replace(final_path)

        applied = [match for match in flat_matches if match.applied]
        return PipelineResult(
            status=JobStatus.DONE,
            output_document=str(final_document),
            report=str(final_json),
            xlsx_report=str(final_xlsx),
            matches=applied,
        )
    except Exception:  # noqa: BLE001 - boundary converts every failure to a safe code
        return PipelineResult(status=JobStatus.FAILED, error_message="pipeline_failed")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


async def pipeline_run(
    file_path: str | Path,
    output_dir: str | Path,
    requested_types: Iterable[EntityType | str],
    llm_client: BaseLLMClient | None = None,
    *,
    answers: Mapping[str, str] | None = None,
    prepared_matches: Iterable[Match] | None = None,
    use_ocr: bool = False,
) -> PipelineResult:
    return await run_pipeline(
        file_path,
        output_dir,
        requested_types,
        llm_client,
        answers=answers,
        prepared_matches=prepared_matches,
        use_ocr=use_ocr,
    )
