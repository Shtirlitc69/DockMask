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
            ocr_pages: list[int] = []
            for page_index, page in enumerate(document):
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
            is_scanned = bool(ocr_pages)
        return ExtractedDocument(
            format=DocumentFormat.PDF,
            blocks=blocks,
            is_scanned=is_scanned,
            ocr_pages=tuple(ocr_pages),
        )


def extract_pdf(file_path: str | Path) -> ExtractedDocument:
    return PdfExtractor().extract(file_path)
