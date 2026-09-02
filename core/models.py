"""Shared, framework-independent domain models for the de-identification pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class JobStatus(str, Enum):
    """Stable machine-readable job states exposed by the API."""

    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_CLARIFICATION = "needs_clarification"
    DONE = "done"
    FAILED = "failed"


class DocumentFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"


class BlockKind(str, Enum):
    DOCX_PARAGRAPH = "docx_paragraph"
    DOCX_TABLE_CELL = "docx_table_cell"
    XLSX_CELL = "xlsx_cell"
    PDF_TEXT_BLOCK = "pdf_text_block"
    PDF_OCR_BLOCK = "pdf_ocr_block"


class EntityType(str, Enum):
    PERSON_NAME = "person_name"
    ORGANIZATION = "organization"
    ADDRESS = "address"
    AMOUNT = "amount"
    INN = "inn"
    KPP = "kpp"
    OGRN = "ogrn"
    PHONE = "phone"
    EMAIL = "email"
    BANK_ACCOUNT = "bank_account"
    BIK = "bik"
    CONTRACT_NUMBER = "contract_number"


class PartyRole(str, Enum):
    SUPPLIER = "supplier"
    BUYER = "buyer"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class Location:
    """Serializable location of a text block inside a source document.

    Structural indexes and ``page_number`` are zero-based internally. UI and
    reports may convert them to one-based values for display.
    """

    paragraph_index: int | None = None
    table_index: int | None = None
    row: int | None = None
    column: int | None = None
    cell_paragraph_index: int | None = None
    sheet_name: str | None = None
    cell_coordinate: str | None = None
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class TextBlock:
    """A stable, serializable piece of extracted document text."""

    block_id: str
    text: str
    kind: BlockKind
    location: Location

    def __post_init__(self) -> None:
        if not self.block_id:
            raise ValueError("block_id must not be empty")


def _validate_span(text: str, start: int, end: int, confidence: float) -> None:
    if not 0 <= start < end:
        raise ValueError("span must satisfy 0 <= start < end")
    if end - start != len(text):
        raise ValueError("span length must match the exact source text length")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(slots=True)
class EntitySpan:
    """An exact entity occurrence returned by a detector or LLM provider."""

    entity_type: EntityType
    text: str
    start: int
    end: int
    source: str = "llm"
    confidence: float = 0.8

    def __post_init__(self) -> None:
        _validate_span(self.text, self.start, self.end, self.confidence)


@dataclass(slots=True)
class Match:
    """A validated, document-aware replacement command for a redactor."""

    block_id: str
    entity_type: EntityType
    text: str
    start: int
    end: int
    replacement: str
    source: str
    confidence: float
    location: Location
    party_role: PartyRole = PartyRole.UNKNOWN
    applied: bool = False

    def __post_init__(self) -> None:
        if not self.block_id:
            raise ValueError("block_id must not be empty")
        if not self.replacement:
            raise ValueError("replacement must not be empty")
        _validate_span(self.text, self.start, self.end, self.confidence)


@dataclass(slots=True)
class ExtractedDocument:
    format: DocumentFormat
    blocks: list[TextBlock] = field(default_factory=list)
    supplier: str | None = None
    buyer: str | None = None
    is_scanned: bool = False


@dataclass(slots=True)
class ClarifyingQuestion:
    question: str
    related_entity_type: EntityType | None = None
    question_id: str = field(default_factory=lambda: str(uuid4()))
    answer: str | None = None

    def __post_init__(self) -> None:
        if not self.question:
            raise ValueError("question must not be empty")


@dataclass(slots=True)
class PipelineResult:
    status: JobStatus
    output_document: str | None = None
    report: str | None = None
    matches: list[Match] = field(default_factory=list)
    open_questions: list[ClarifyingQuestion] = field(default_factory=list)
    error_message: str | None = None


@dataclass(slots=True)
class Job:
    job_id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.QUEUED
    source_filename: str = ""
    document_format: DocumentFormat | None = None
    entity_types_requested: list[EntityType] = field(default_factory=list)
    questions: list[ClarifyingQuestion] = field(default_factory=list)
    result_file_path: str | None = None
    report_file_path: str | None = None
    total_replacements: int = 0
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class ReportEntry:
    entity_type: EntityType
    original_value: str
    replacement: str
    location: Location
    source: str
    confidence: float
    party_role: PartyRole = PartyRole.UNKNOWN
    applied: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
