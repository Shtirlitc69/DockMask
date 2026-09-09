"""Text PDF extractor based on PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz

from core.models import BlockKind, DocumentFormat, ExtractedDocument, Location, TextBlock


class PdfExtractor:
    """Extract positioned text blocks from a non-scanned PDF."""

    def extract(self, file_path: str | Path) -> ExtractedDocument:
        blocks: list[TextBlock] = []
        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document):
                for block_index, raw in enumerate(page.get_text("blocks", sort=True)):
                    x0, y0, x1, y1, text, *_ = raw
                    if not isinstance(text, str) or not text.strip():
                        continue
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
            is_scanned = bool(document.page_count) and not blocks
        return ExtractedDocument(
            format=DocumentFormat.PDF,
            blocks=blocks,
            is_scanned=is_scanned,
        )


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    return PdfExtractor().extract(file_path)
