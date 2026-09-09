"""Real redaction for text PDFs using PyMuPDF annotations."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import fitz

from core.models import Match


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
                        text=match.replacement,
                        fontname="helv",
                        fontsize=8,
                        fill=(1, 1, 0.55),
                        text_color=(0, 0, 0),
                        cross_out=False,
                    )
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
                    text=match.replacement,
                    fontname="helv",
                    fontsize=8,
                    fill=(1, 1, 0.55),
                    text_color=(0, 0, 0),
                    cross_out=False,
                )
                touched_pages.add(location.page_number)
                match.applied = True
        for page_number in touched_pages:
            document[page_number].apply_redactions()
        target.parent.mkdir(parents=True, exist_ok=True)
        document.save(target, garbage=4, deflate=True)
    finally:
        document.close()
    return target
