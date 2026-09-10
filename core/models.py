"""Общие доменные модели, независимые от фреймворка, для конвейера деидентификации."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4


class JobStatus(str, Enum):
    """Stable task statuses exposed through the API."""

    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_CLARIFICATION = "needs_clarification"
    CANCELLED = "cancelled"
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


ENTITY_MARKER_PREFIXES: dict[EntityType, str] = {
    EntityType.PERSON_NAME: "ФИО",
    EntityType.ORGANIZATION: "ОРГАНИЗАЦИЯ",
    EntityType.ADDRESS: "АДРЕС",
    EntityType.AMOUNT: "СУММА",
    EntityType.INN: "ИНН",
    EntityType.KPP: "КПП",
    EntityType.OGRN: "ОГРН",
    EntityType.PHONE: "ТЕЛЕФОН",
    EntityType.EMAIL: "ЭЛЕКТРОННАЯ_ПОЧТА",
    EntityType.BANK_ACCOUNT: "РАСЧЁТНЫЙ_СЧЁТ",
    EntityType.BIK: "БИК",
    EntityType.CONTRACT_NUMBER: "НОМЕР_ДОГОВОРА",
}

ENTITY_DISPLAY_NAMES: dict[EntityType, str] = {
    EntityType.PERSON_NAME: "ФИО",
    EntityType.ORGANIZATION: "Организация",
    EntityType.ADDRESS: "Адрес",
    EntityType.AMOUNT: "Сумма",
    EntityType.INN: "ИНН",
    EntityType.KPP: "КПП",
    EntityType.OGRN: "ОГРН",
    EntityType.PHONE: "Телефон",
    EntityType.EMAIL: "Электронная почта",
    EntityType.BANK_ACCOUNT: "Расчётный счёт",
    EntityType.BIK: "БИК",
    EntityType.CONTRACT_NUMBER: "Номер договора",
}


class PartyRole(str, Enum):
    SUPPLIER = "supplier"
    BUYER = "buyer"
    UNKNOWN = "unknown"


PARTY_ROLE_DISPLAY_NAMES: dict[PartyRole, str] = {
    PartyRole.SUPPLIER: "Поставщик",
    PartyRole.BUYER: "Покупатель",
    PartyRole.UNKNOWN: "Не определено",
}


@dataclass(slots=True, frozen=True)
class Location:
    """Сериализуемое расположение текстового блока внутри исходного документа.

    Структурные индексы и ``page_number`` внутренне считаются нуль-индексированными.
    UI и отчёты могут преобразовывать их в однозначные (one-based) значения для отображения.
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
    ocr_words: tuple[tuple[int, int, float, float, float, float], ...] | None = None


@dataclass(slots=True)
class TextBlock:
    """Стабильный, сериализуемый фрагмент извлечённого текста документа."""

    block_id: str
    text: str
    kind: BlockKind
    location: Location

    def __post_init__(self) -> None:
        if not self.block_id:
            raise ValueError("block_id не может быть пустым")


def _validate_span(text: str, start: int, end: int, confidence: float) -> None:
    if not 0 <= start < end:
        raise ValueError("span должен удовлетворять условию 0 <= start < end")
    if end - start != len(text):
        raise ValueError("длина span должна точно соответствовать длине исходного текста")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence должен быть в диапазоне от 0.0 до 1.0")


@dataclass(slots=True)
class EntitySpan:
    """Точное вхождение сущности, возвращённое детектором или провайдером LLM."""

    entity_type: EntityType
    text: str
    start: int
    end: int
    source: str = "llm"
    confidence: float = 0.8
    party_role: PartyRole = PartyRole.UNKNOWN

    def __post_init__(self) -> None:
        _validate_span(self.text, self.start, self.end, self.confidence)


@dataclass(slots=True)
class Match:
    """Проверенная команда замены, учитывающая документ, для редактора."""

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
            raise ValueError("block_id не может быть пустым")
        if not self.replacement:
            raise ValueError("replacement не может быть пустым")
        _validate_span(self.text, self.start, self.end, self.confidence)


@dataclass(slots=True)
class ExtractedDocument:
    format: DocumentFormat
    blocks: list[TextBlock] = field(default_factory=list)
    supplier: str | None = None
    buyer: str | None = None
    is_scanned: bool = False
    ocr_pages: tuple[int, ...] = ()


@dataclass(slots=True)
class ClarifyingQuestion:
    question: str
    related_entity_type: EntityType | None = None
    question_id: str = field(default_factory=lambda: str(uuid4()))
    answer: str | None = None
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.question:
            raise ValueError("question не может быть пустым")


@dataclass(slots=True)
class PipelineResult:
    status: JobStatus
    output_document: str | None = None
    report: str | None = None
    xlsx_report: str | None = None
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
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


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
            raise ValueError("confidence должен быть в диапазоне от 0.0 до 1.0")
