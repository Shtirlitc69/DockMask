"""JSON and XLSX reports for successfully applied redactions."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.models import ENTITY_DISPLAY_NAMES, PARTY_ROLE_DISPLAY_NAMES, Location, Match

REPORT_COLUMNS = (
    "№",
    "Тип сущности",
    "Исходное значение",
    "Замена",
    "Роль",
    "Источник",
    "Уверенность",
    "Расположение",
    "Применено",
)


def location_to_dict(location: Location | None) -> dict[str, Any]:
    if location is None:
        return {}
    return {
        "paragraph_index": location.paragraph_index,
        "table_index": location.table_index,
        "row": location.row,
        "column": location.column,
        "cell_paragraph_index": location.cell_paragraph_index,
        "sheet_name": location.sheet_name,
        "cell_coordinate": location.cell_coordinate,
        "page_number": location.page_number,
        "bbox": list(location.bbox) if location.bbox is not None else None,
        "ocr_words": [list(item) for item in location.ocr_words] if location.ocr_words else None,
    }


def format_location(location: Location | None) -> str:
    """Convert zero-based structural coordinates to a human-readable value."""

    if location is None:
        return "Не указано"
    if location.sheet_name or location.cell_coordinate:
        return f"Лист «{location.sheet_name or '?'}», ячейка {location.cell_coordinate or '?'}"
    if location.table_index is not None:
        result = (
            f"Таблица {location.table_index + 1}, строка {(location.row or 0) + 1}, "
            f"столбец {(location.column or 0) + 1}"
        )
        if location.cell_paragraph_index is not None:
            result += f", абзац {location.cell_paragraph_index + 1}"
        return result
    if location.paragraph_index is not None:
        return f"Абзац {location.paragraph_index + 1}"
    if location.page_number is not None:
        result = f"Страница {location.page_number + 1}"
        if location.bbox is not None:
            result += ", область " + ", ".join(f"{value:.1f}" for value in location.bbox)
        return result
    return "Не указано"


def applied_matches(matches: Iterable[Match]) -> list[Match]:
    return [match for match in matches if match.applied]


def flatten_applied(matches_by_block: Mapping[str, Iterable[Match]]) -> list[Match]:
    return applied_matches(
        match for block_matches in matches_by_block.values() for match in block_matches
    )


class ReportGenerator:
    """Build JSON data and formatted XLSX reports from the same matches."""

    @staticmethod
    def build(matches: Iterable[Match], *, applied_only: bool = False) -> list[dict[str, Any]]:
        source = applied_matches(matches) if applied_only else list(matches)
        return [
            {
                "entity_type": match.entity_type.value,
                "original_value": match.text,
                "replacement": match.replacement,
                "location": location_to_dict(match.location),
                "source": match.source,
                "confidence": match.confidence,
                "party_role": match.party_role.value,
                "entity_id": match.entity_id,
                "organization_id": match.organization_id,
                "evidence": [
                    {
                        "kind": item.kind.value,
                        "block_id": item.block_id,
                        "subject_id": item.subject_id,
                        "object_id": item.object_id,
                        "value": item.value,
                        "confidence": item.confidence,
                    }
                    for item in match.evidence
                ],
                "conflict": match.conflict,
                "applied": bool(match.applied),
            }
            for match in source
        ]

    @staticmethod
    def generate(matches: Iterable[Match]) -> list[dict[str, Any]]:
        return ReportGenerator.build(matches)

    @staticmethod
    def to_json(
        matches: Iterable[Match],
        *,
        indent: int = 2,
        applied_only: bool = False,
    ) -> str:
        return json.dumps(
            ReportGenerator.build(matches, applied_only=applied_only),
            ensure_ascii=False,
            indent=indent,
        )

    @staticmethod
    def write_report(
        path: str | Path,
        matches: Iterable[Match],
        *,
        applied_only: bool = False,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            ReportGenerator.to_json(matches, applied_only=applied_only),
            encoding="utf-8",
        )
        return target

    @staticmethod
    def write_xlsx(path: str | Path, matches: Iterable[Match]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Замены"
        sheet.append(REPORT_COLUMNS)

        header_fill = PatternFill("solid", fgColor="1F4E78")
        header_font = Font(color="FFFFFF", bold=True)
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for number, match in enumerate(applied_matches(matches), start=1):
            sheet.append(
                (
                    number,
                    ENTITY_DISPLAY_NAMES[match.entity_type],
                    match.text,
                    match.replacement,
                    PARTY_ROLE_DISPLAY_NAMES[match.party_role],
                    match.source,
                    match.confidence,
                    format_location(match.location),
                    True,
                )
            )
            sheet.cell(sheet.max_row, 7).number_format = "0.00%"

        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:I{max(sheet.max_row, 1)}"
        widths = (7, 21, 32, 24, 15, 18, 16, 42, 13)
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

        workbook.save(target)
        workbook.close()
        return target


def generate_report(
    matches_by_block: dict[str, list[Match]],
    output_path: Path,
) -> Path:
    """Create the M8 XLSX report containing only applied matches."""

    return ReportGenerator.write_xlsx(output_path, flatten_applied(matches_by_block))


def build_report(matches: Iterable[Match]) -> list[dict[str, Any]]:
    return ReportGenerator.build(matches)


def write_report(path: str | Path, matches: Iterable[Match]) -> Path:
    return ReportGenerator.write_report(path, matches)
