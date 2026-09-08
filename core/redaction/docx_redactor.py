"""DOCX redactor that preserves the original document and writes a masked copy."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.text.paragraph import Paragraph

from core.models import Match


class DocxRedactor:
    """Apply redaction masks to a DOCX while keeping the source document intact."""

    def redact(
        self,
        source_file: str | Path,
        output_file: str | Path,
        matches_by_block: dict[str, list[Match]],
    ) -> Path:
        source_path = Path(source_file)
        target_path = Path(output_file)
        if source_path.resolve() == target_path.resolve():
            raise ValueError("output_file must differ from source_file")
        document = Document(str(source_path))

        for block_id, matches in matches_by_block.items():
            if not matches:
                continue
            target = self._resolve_target(document, block_id)
            if target is None:
                continue
            if isinstance(target, Paragraph):
                self._apply_to_paragraph(target, matches)
                continue
            self._apply_to_cell(target, matches)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(target_path))
        return target_path

    @staticmethod
    def _resolve_target(document: Document, block_id: str):
        if block_id.startswith("docx_paragraph_"):
            index = int(block_id.removeprefix("docx_paragraph_"))
            paragraphs = document.paragraphs
            if 0 <= index < len(paragraphs):
                return paragraphs[index]
            return None

        if block_id.startswith("docx_table_"):
            segments = block_id.removeprefix("docx_table_").split("_r")
            if len(segments) != 2:
                return None
            table_index_str, tail = segments
            try:
                table_index = int(table_index_str)
            except ValueError:
                return None
            if "_c" not in tail:
                return None
            row_part, col_part = tail.split("_c", 1)
            try:
                row_index = int(row_part)
                column_index = int(col_part)
            except ValueError:
                return None
            if 0 <= table_index < len(document.tables):
                table = document.tables[table_index]
                if 0 <= row_index < len(table.rows):
                    row = table.rows[row_index]
                    if 0 <= column_index < len(row.cells):
                        return row.cells[column_index]
            return None
        return None

    @staticmethod
    def _apply_to_paragraph(paragraph: Paragraph, matches: list[Match]) -> None:
        if not matches:
            return
        text = paragraph.text
        if not text:
            return

        ordered = sorted(
            (match for match in matches if 0 <= match.start < match.end <= len(text)),
            key=lambda match: (match.start, match.end),
        )
        if not ordered:
            return

        pieces: list[str] = []
        cursor = 0
        for match in ordered:
            if match.start < cursor:
                continue
            pieces.append(text[cursor : match.start])
            pieces.append(match.replacement)
            cursor = match.end
        pieces.append(text[cursor:])

        paragraph.text = ""
        for index, piece in enumerate(pieces):
            run = paragraph.add_run(piece)
            if index % 2 == 1:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                run.font.bold = True
        for match in ordered:
            match.applied = True

    @staticmethod
    def _apply_to_cell(cell, matches: list[Match]) -> None:
        if not matches:
            return
        paragraphs = cell.paragraphs
        if not paragraphs:
            return

        for paragraph in paragraphs:
            DocxRedactor._apply_to_paragraph(paragraph, matches)


def redact_docx(
    source_file: str | Path,
    output_file: str | Path,
    matches_by_block: dict[str, list[Match]],
) -> Path:
    return DocxRedactor().redact(source_file, output_file, matches_by_block)
