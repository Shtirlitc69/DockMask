"""DOCX экстрактор, извлекающий
текстовые блоки из DOCX документов."""

from pathlib import Path

from docx import Document

from core.models import (
    BlockKind,
    DocumentFormat,
    ExtractedDocument,
    Location,
    TextBlock,
)


class DocxExtractor:
    """
    Задача - извлекать текстовые блоки из DOCX документов и
    представлять их в виде объектов TextBlock.
    """

    def extract(self, file_path: str | Path) -> ExtractedDocument:
        path = Path(file_path)
        document = Document(str(path))

        blocks: list[TextBlock] = []

        # Абзацы
        for paragraph_index, paragraph in enumerate(document.paragraphs):
            text = paragraph.text.strip()
            if not text:
                continue
            blocks.append(
                TextBlock(
                    block_id=f"docx_paragraph_{paragraph_index}",
                    text=text,
                    kind=BlockKind.DOCX_PARAGRAPH,
                    location=Location(paragraph_index=paragraph_index),
                )
            )

        # Таблицы
        for table_index, table in enumerate(document.tables):
            for row_index, row in enumerate(table.rows):
                for column_index, cell in enumerate(row.cells):
                    text = cell.text.strip()
                    if not text:
                        continue
                    blocks.append(
                        TextBlock(
                            block_id=f"docx_table_{table_index}_r{row_index}_c{column_index}",
                            text=text,
                            kind=BlockKind.DOCX_TABLE_CELL,
                            location=Location(
                                table_index=table_index,
                                row=row_index,
                                column=column_index,
                            ),
                        )
                    )

        return ExtractedDocument(
            format=DocumentFormat.DOCX,
            blocks=blocks,
        )


def extract_docx(file_path: str | Path) -> ExtractedDocument:
    return DocxExtractor().extract(file_path)