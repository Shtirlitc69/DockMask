"""
Файл для создания всех классов взаимодействия с бд.
"""


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4


class JobStatus(str, Enum):
    """
    Класс для статусов задач.
    """

    PENDING = "Ожидание выполнения"
    ANALYZING = "Анализируется"
    DETECTING = "Обнаружение"
    NEEDS_INPUT = "Нужны данные"
    REDACTING = "Редактируется"
    DONE = "Готово"
    FAILED = "Ошибка"

class DocumentFormat(str, Enum):
    """
    Класс для форматов файлов.
    """

    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"

class EntityType(str, Enum):
    """
    Класс для типов сущностей.
    Заполню как пришлют датасеты
    """
    pass

class PartyRole(str, Enum):
    """
    Роль стороны в тендерном документе.
    """
    SUPPLIER = "supplier"   # поставщик
    BUYER = "buyer"         # покупатель
    UNKNOWN = "unknown"

@dataclass # нужен для того, чтобы можно было создавать объекты класса без явного вызова конструктора
class Location:
    """
    Класс для хранения строк найденных в тексте, которые являются адресами.
    """
    # Общее для всех типов файлов
    page_number: int
    #PDF
    paragraph_index: Optional[int] = None
    #DOCX
    table_index: Optional[str] = None
    #DOCX/XLSX
    row: Optional[int] = None
    #XLSX/таблицы
    column: Optional[int] = None
    sheet_name: Optional[str] = None
    run_index: Optional[int] = None
    #DOCX
    bbox: Optional[tuple[float, float, float, float]] = None

@dataclass
class TextBlock:
    """Один связный кусок текста, извлеченный из документа —
    абзац DOCX, ячейка таблицы XLSX, текстовый блок PDF."""
    id: str = field(default_factory=lambda: str(uuid4()))
    text: str = ""
    location: Location = field(default_factory=Location)
    is_table_cell: bool = False

@dataclass
class ExtractedDocument:
    """Результат шага «Анализ документа» — то, что extractor отдаёт
    дальше в detector."""
    format: DocumentFormat
    blocks: list[TextBlock] = field(default_factory=list)
    supplier: Optional[str] = None
    buyer: Optional[str] = None
    is_scanned: bool = False   # True → перед анализом нужен OCR



@dataclass
class EntitySpan:
    """Найденная сущность внутри текста одного TextBlock."""
    text_block_id: str
    entity_type: EntityType
    value: str  # сам найденный текст, напр. "ООО Ромашка"
    start: int  # индекс начала в TextBlock.text
    end: int  # индекс конца (exclusive)
    confidence: float = 1.0  # 1.0 для regex-правил, <1.0 для LLM/OCR
    party_role: PartyRole = PartyRole.UNKNOWN
    source: str = "rule"  # "rule" | "llm" | "ocr"


@dataclass
class Match:
    """Связка «что нашли + где именно заменить в файле + чем заменить».
    Это то, что реально уходит в redactor."""
    entity: EntitySpan
    location: Location
    replacement: str  # напр. "[ОРГАНИЗАЦИЯ_1]"
    applied: bool = False  # True после того, как redactor внёс замену

@dataclass
class ClarifyingQuestion:
    """Вопрос пользователю, если данных не хватает
    (например, не удалось определить, кто поставщик, а кто покупатель)."""
    id: str = field(default_factory=lambda: str(uuid4()))
    question: str = ""
    related_entity_type: Optional[EntityType] = None
    answer: Optional[str] = None

@dataclass
class Job:
    id: str = field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.PENDING

    source_filename: str = ""
    document_format: Optional[DocumentFormat] = None
    entity_types_requested: list[EntityType] = field(default_factory=list)

    extracted: Optional[ExtractedDocument] = None
    matches: list[Match] = field(default_factory=list)
    questions: list[ClarifyingQuestion] = field(default_factory=list)

    result_file_path: Optional[str] = None
    report_file_path: Optional[str] = None

    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class ReportEntry:
    """Одна строка в итоговом отчёте о заменах."""
    entity_type: EntityType
    original_value: str
    replacement: str
    location: Location
