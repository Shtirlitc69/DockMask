"""Lightweight coordinator for extraction, analysis, clarification and redaction."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import ParamSpec, TypeVar

from core.detectors.entity_detector import detect_all
from core.detectors.party_identifier import identify_parties
from core.extractors.docx_extractor import extract_docx
from core.extractors.ocr.base import OcrProcessingError, OcrProvider, OcrUnavailableError
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
    TextBlock,
)
from core.redaction.docx_redactor import redact_docx
from core.redaction.pdf_redactor import redact_pdf
from core.redaction.xlsx_redactor import redact_xlsx
from core.report.report_generator import ReportGenerator, format_location, generate_report
from llm.base import BaseLLMClient
from llm.http_utils import LLMContextLimitError, LLMHTTPError, LLMProviderError
from llm.structured import LLMResponseError

LOGGER = logging.getLogger(__name__)
P = ParamSpec("P")
T = TypeVar("T")


async def _file_operation(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Drain a running file operation before cancellation allows directory cleanup."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise

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


class PipelineCancelled(RuntimeError):
    """Raised cooperatively when a job has been cancelled."""


def _check_cancelled(cancel_check: Callable[[], None] | None) -> None:
    if cancel_check is not None:
        cancel_check()


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
    return f"party:{match.entity_type.value}:{match.replacement}"


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
    blocks: Iterable[TextBlock],
) -> list[ClarifyingQuestion]:
    questions: list[ClarifyingQuestion] = []
    blocks_by_id = {block.block_id: block for block in blocks}
    added: set[str] = set()
    for match in _flatten_matches(matches_by_block):
        if match.entity_type not in {EntityType.ORGANIZATION, EntityType.PERSON_NAME}:
            continue
        question_id = _question_id(match)
        if (
            match.party_role is not PartyRole.UNKNOWN
            or question_id in answered
            or question_id in added
        ):
            continue
        added.add(question_id)
        block = blocks_by_id.get(match.block_id)
        context_text: str | None = None
        highlight_start: int | None = None
        highlight_end: int | None = None
        if block is not None:
            line_start = block.text.rfind("\n", 0, match.start) + 1
            line_end = block.text.find("\n", match.end)
            if line_end < 0:
                line_end = len(block.text)
            raw_line = block.text[line_start:line_end]
            leading_spaces = len(raw_line) - len(raw_line.lstrip())
            context_text = raw_line.strip()
            highlight_start = match.start - line_start - leading_spaces
            highlight_end = match.end - line_start - leading_spaces
            if not (
                context_text
                and 0 <= highlight_start < highlight_end <= len(context_text)
            ):
                context_text = block.text
                highlight_start = match.start
                highlight_end = match.end
        questions.append(
            ClarifyingQuestion(
                question=f"Определите роль стороны «{match.text}» ({match.replacement}).",
                related_entity_type=match.entity_type,
                question_id=question_id,
                options=tuple(item.value for item in PartyRole),
                context_text=context_text,
                context_location=format_location(match.location),
                highlight_start=highlight_start,
                highlight_end=highlight_end,
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
    ocr_provider: OcrProvider | None = None,
    cancel_check: Callable[[], None] | None = None,
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
        _check_cancelled(cancel_check)
        extracted = await _file_operation(_EXTRACTORS[document_format], source)
        _check_cancelled(cancel_check)
        if extracted.is_scanned:
            if not use_ocr:
                return PipelineResult(status=JobStatus.FAILED, error_message="ocr_required")
            if ocr_provider is None:
                return PipelineResult(status=JobStatus.FAILED, error_message="ocr_unavailable")
            for page_number in extracted.ocr_pages:
                _check_cancelled(cancel_check)
                page_blocks = await _file_operation(
                    ocr_provider.extract_page,
                    source,
                    page_number,
                    cancel_check=cancel_check,
                )
                if not page_blocks:
                    return PipelineResult(status=JobStatus.FAILED, error_message="ocr_no_text")
                extracted.blocks.extend(page_blocks)

        if prepared_matches is None:
            matches_by_block = await detect_all(
                extracted.blocks,
                normalized_types,
                llm_client,
                cancel_check=cancel_check,
            )
            _check_cancelled(cancel_check)
            await identify_parties(extracted.blocks, matches_by_block, llm_client)
        else:
            matches_by_block: dict[str, list[Match]] = {}
            for match in prepared_matches:
                matches_by_block.setdefault(match.block_id, []).append(match)
        answered = _apply_answers(matches_by_block, answers or {})
        questions = _role_questions(matches_by_block, answered, extracted.blocks)
        if questions:
            return PipelineResult(
                status=JobStatus.NEEDS_CLARIFICATION,
                matches=_flatten_matches(matches_by_block),
                open_questions=questions,
            )

        staged_document = staging / f"{source.stem}.redacted{source.suffix.lower()}"
        await _file_operation(
            _REDACTORS[document_format],
            source,
            staged_document,
            matches_by_block,
        )
        _check_cancelled(cancel_check)
        flat_matches = _flatten_matches(matches_by_block)
        staged_json = staging / f"{source.stem}.report.json"
        staged_xlsx = staging / f"{source.stem}.report.xlsx"
        await _file_operation(
            ReportGenerator.write_report,
            staged_json,
            flat_matches,
            applied_only=True,
        )
        await _file_operation(generate_report, matches_by_block, staged_xlsx)
        _check_cancelled(cancel_check)

        final_document = output_root / staged_document.name
        final_json = output_root / staged_json.name
        final_xlsx = output_root / staged_xlsx.name
        for staged_path, final_path in (
            (staged_document, final_document),
            (staged_json, final_json),
            (staged_xlsx, final_xlsx),
        ):
            _check_cancelled(cancel_check)
            staged_path.replace(final_path)

        applied = [match for match in flat_matches if match.applied]
        return PipelineResult(
            status=JobStatus.DONE,
            output_document=str(final_document),
            report=str(final_json),
            xlsx_report=str(final_xlsx),
            matches=applied,
        )
    except PipelineCancelled:
        raise
    except OcrUnavailableError:
        return PipelineResult(status=JobStatus.FAILED, error_message="ocr_unavailable")
    except OcrProcessingError:
        return PipelineResult(status=JobStatus.FAILED, error_message="ocr_failed")
    except LLMContextLimitError:
        LOGGER.error(
            "pipeline_provider_context_limit provider=%s",
            llm_client.provider_name,
        )
        return PipelineResult(status=JobStatus.FAILED, error_message="provider_context_limit")
    except LLMHTTPError as exc:
        if llm_client.provider_name == "gigachat":
            code = {
                401: "gigachat_authentication_failed",
                402: "gigachat_payment_required",
                403: "gigachat_permission_denied",
                429: "gigachat_rate_limited",
            }.get(exc.status_code, "provider_unavailable")
        else:
            code = "provider_unavailable"
        LOGGER.error(
            "pipeline_provider_http_failed provider=%s status=%s",
            llm_client.provider_name,
            exc.status_code,
        )
        return PipelineResult(status=JobStatus.FAILED, error_message=code)
    except LLMResponseError:
        LOGGER.error("pipeline_provider_invalid_response provider=%s", llm_client.provider_name)
        return PipelineResult(status=JobStatus.FAILED, error_message="provider_invalid_response")
    except LLMProviderError as exc:
        LOGGER.error(
            "pipeline_provider_failed provider=%s exception_type=%s",
            llm_client.provider_name,
            type(exc).__name__,
        )
        return PipelineResult(status=JobStatus.FAILED, error_message="provider_unavailable")
    except Exception as exc:  # noqa: BLE001 - boundary converts every failure to a safe code
        LOGGER.error("pipeline_failed exception_type=%s", type(exc).__name__)
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
    ocr_provider: OcrProvider | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> PipelineResult:
    return await run_pipeline(
        file_path,
        output_dir,
        requested_types,
        llm_client,
        answers=answers,
        prepared_matches=prepared_matches,
        use_ocr=use_ocr,
        ocr_provider=ocr_provider,
        cancel_check=cancel_check,
    )
