"""Real redaction for text PDFs using PyMuPDF annotations."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import fitz

from core.models import Match


def _cyrillic_font_path() -> Path:
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("arial.ttf", "segoeui.ttf"):
        candidate = fonts / name
        if candidate.is_file():
            return candidate
    raise RuntimeError("cyrillic_pdf_font_unavailable")


def redact_pdf(
    source_file: str | Path,
    output_file: str | Path,
    matches_by_block: dict[str, list[Match]],
) -> Path:
    source = Path(source_file)
    target = Path(output_file)
    if source.resolve() == target.resolve():
        raise ValueError("output_file must differ from source_file")

    document = fitz.open(source)
    try:
        occurrences: defaultdict[tuple[int, str], int] = defaultdict(int)
        touched_pages: set[int] = set()
        replacements: defaultdict[int, list[tuple[fitz.Rect, str]]] = defaultdict(list)
        for block_id, matches in matches_by_block.items():
            for match in sorted(matches, key=lambda item: (item.start, item.end)):
                location = match.location
                if location.page_number is None or location.page_number >= document.page_count:
                    continue
                page = document[location.page_number]
                if location.ocr_words:
                    word_rects = [
                        fitz.Rect(word[2:])
                        for word in location.ocr_words
                        if word[0] < match.end and word[1] > match.start
                    ]
                    if not word_rects:
                        continue
                    candidate = word_rects[0]
                    for word_rect in word_rects[1:]:
                        candidate |= word_rect
                    page.add_redact_annot(
                        candidate,
                        fill=(1, 1, 0.55),
                        cross_out=False,
                    )
                    replacements[location.page_number].append((candidate, match.replacement))
                    touched_pages.add(location.page_number)
                    match.applied = True
                    continue
                candidates = page.search_for(match.text)
                if location.bbox is not None:
                    block_rect = fitz.Rect(location.bbox)
                    candidates = [rect for rect in candidates if rect.intersects(block_rect)]
                key = (location.page_number, f"{block_id}\0{match.text}")
                index = occurrences[key]
                occurrences[key] += 1
                if index >= len(candidates):
                    continue
                page.add_redact_annot(
                    candidates[index],
                    fill=(1, 1, 0.55),
                    cross_out=False,
                )
                replacements[location.page_number].append(
                    (candidates[index], match.replacement)
                )
                touched_pages.add(location.page_number)
                match.applied = True
        font_path = _cyrillic_font_path() if replacements else None
        font = fitz.Font(fontfile=str(font_path)) if font_path else None
        for page_number in touched_pages:
            page = document[page_number]
            page.apply_redactions()
            for rect, replacement in replacements[page_number]:
                assert font is not None and font_path is not None
                unit_width = max(font.text_length(replacement, fontsize=1), 1)
                font_size = min(8.0, max(3.0, rect.width / unit_width * 0.95))
                page.insert_textbox(
                    rect,
                    replacement,
                    fontname="dockmask",
                    fontfile=str(font_path),
                    fontsize=font_size,
                    color=(0, 0, 0),
                    overlay=True,
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        document.save(target, garbage=4, deflate=True)
    finally:
        document.close()
    return target
