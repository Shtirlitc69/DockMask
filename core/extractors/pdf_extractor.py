"""Text PDF extractor based on PyMuPDF."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from core.context import enrich_context
from core.models import BlockKind, DocumentFormat, ExtractedDocument, Location, TextBlock


def _table_context(page, blocks: list[TextBlock]) -> None:
    """Attach cell headers and exact money spans without rebuilding PDF text blocks."""
    tables = page.find_tables().tables
    raw_blocks = page.get_text("rawdict", sort=True)["blocks"]
    for table_index, table in enumerate(tables):
        rows = table.extract()
        if not rows:
            continue
        headers = rows[0]
        for row_index, row in enumerate(table.rows[1:], 1):
            for column, cell in enumerate(row.cells):
                if cell is None:
                    continue
                header = headers[column] or ""
                region = fitz.Rect(cell)
                for block in blocks:
                    if not fitz.Rect(block.location.bbox).intersects(region):
                        continue
                    block.context.setdefault("table_cells", []).append(
                        {
                            "table": table_index,
                            "row": row_index,
                            "column": column,
                            "header": header,
                            "bbox": list(cell),
                        }
                    )
                    for raw in raw_blocks:
                        if raw.get("type") != 0 or any(
                            abs(a - b) > 0.1 for a, b in zip(raw["bbox"], block.location.bbox)
                        ):
                            continue
                        offset = 0
                        for line in raw["lines"]:
                            chars = [c for span in line["spans"] for c in span["chars"]]
                            selected = [
                                i
                                for i, c in enumerate(chars)
                                if region.contains(
                                    fitz.Rect(c["bbox"]).tl
                                    + (fitz.Rect(c["bbox"]).br - fitz.Rect(c["bbox"]).tl) * 0.5
                                )
                            ]
                            if selected:
                                start, end = offset + min(selected), offset + max(selected) + 1
                                value = block.text[start:end]
                                block.context.setdefault("cell_spans", []).append(
                                    {
                                        "start": start,
                                        "end": end,
                                        "table": table_index,
                                        "row": row_index,
                                        "column": column,
                                    }
                                )
                                if re.search(
                                    r"цена|сумма|стоимость", header, re.IGNORECASE
                                ) and re.fullmatch(r"\s*\d[\d\s.,]*\s*", value):
                                    left = len(value) - len(value.lstrip())
                                    block.context.setdefault("money_spans", []).append(
                                        [start + left, start + len(value.rstrip())]
                                    )
                            offset += len(chars) + 1


class PdfExtractor:
    """Extract positioned text blocks from a non-scanned PDF."""

    def extract(self, file_path: str | Path) -> ExtractedDocument:
        blocks: list[TextBlock] = []
        with fitz.open(file_path) as document:
            ocr_pages: list[int] = []
            for page_index, page in enumerate(document):
                page_start = len(blocks)
                page_has_text = False
                for block_index, raw in enumerate(page.get_text("blocks", sort=True)):
                    x0, y0, x1, y1, text, *_ = raw
                    if not isinstance(text, str) or not text.strip():
                        continue
                    page_has_text = True
                    blocks.append(
                        TextBlock(
                            block_id=f"pdf_page_{page_index}_block_{block_index}",
                            text=text,
                            kind=BlockKind.PDF_TEXT_BLOCK,
                            location=Location(
                                page_number=page_index,
                                bbox=(float(x0), float(y0), float(x1), float(y1)),
                            ),
                        )
                    )
                if not page_has_text:
                    ocr_pages.append(page_index)
                else:
                    _table_context(page, blocks[page_start:])
            is_scanned = bool(ocr_pages)
        enrich_context(blocks)
        return ExtractedDocument(
            format=DocumentFormat.PDF,
            blocks=blocks,
            is_scanned=is_scanned,
            ocr_pages=tuple(ocr_pages),
        )


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    return PdfExtractor().extract(file_path)
