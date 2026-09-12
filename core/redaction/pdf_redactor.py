"""Real redaction for text PDFs using PyMuPDF annotations."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import fitz

from core.models import Match
from core.redaction.options import LabelStyle, display_label


def _cyrillic_font_path() -> Path:
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name in ("arial.ttf", "segoeui.ttf"):
        candidate = fonts / name
        if candidate.is_file():
            return candidate
    raise RuntimeError("cyrillic_pdf_font_unavailable")


def _text_rects(raw_blocks: list[dict], match: Match) -> list[fitz.Rect]:
    """Map extractor offsets to characters, including every line of one occurrence."""
    for block in raw_blocks:
        if block.get("type") != 0:
            continue
        if match.location.bbox is not None and any(
            abs(a - b) > 0.1 for a, b in zip(block["bbox"], match.location.bbox)
        ):
            continue
        text = ""
        lines = []
        for line in block["lines"]:
            chars = [char for span in line["spans"] for char in span["chars"]]
            lines.append((len(text), chars))
            text += "".join(char["c"] for char in chars) + "\n"
        if text[match.start : match.end] != match.text:
            continue
        rects = []
        for offset, chars in lines:
            selected = chars[max(0, match.start - offset) : max(0, match.end - offset)]
            if selected:
                rect = fitz.Rect(selected[0]["bbox"])
                for char in selected[1:]:
                    rect |= fitz.Rect(char["bbox"])
                rects.append(rect)
        return rects
    return []


def _ocr_rects(match: Match) -> list[fitz.Rect]:
    # Keep lines separate: a union across lines erases unrelated surrounding text.
    rects: list[fitz.Rect] = []
    for start, end, *bbox in match.location.ocr_words or ():
        if start >= match.end or end <= match.start:
            continue
        rect = fitz.Rect(bbox)
        if rects and abs(rect.y0 - rects[-1].y0) < min(rect.height, rects[-1].height) * 0.5:
            rects[-1] |= rect
        else:
            rects.append(rect)
    return rects


def _draw_label(page, rect, label, font, font_path):
    if not label:
        return
    # Fit actual font metrics and centre the baseline; never ignore textbox failure.
    width = max(font.text_length(label, fontsize=1), 1)
    size = min(10.0, (rect.width - 2) / width, (rect.height - 1) / (font.ascender - font.descender))
    if size <= 0:
        return
    x = rect.x0 + (rect.width - width * size) / 2
    y = rect.y0 + (rect.height - size * (font.ascender - font.descender)) / 2
    y += size * font.ascender
    page.insert_text(
        (x, y),
        label,
        fontname="dockmask",
        fontfile=str(font_path),
        fontsize=size,
        color=(0, 0, 0),
        overlay=True,
    )


def redact_pdf(
    source_file: str | Path,
    output_file: str | Path,
    matches_by_block: dict[str, list[Match]],
    *,
    label_style: LabelStyle | str = LabelStyle.FULL,
) -> Path:
    source, target = Path(source_file), Path(output_file)
    if source.resolve() == target.resolve():
        raise ValueError("output_file must differ from source_file")
    style = LabelStyle(label_style)
    with fitz.open(source) as document:
        replacements = defaultdict(list)
        page_blocks = {}
        for matches in matches_by_block.values():
            for match in sorted(matches, key=lambda item: (item.start, item.end)):
                number = match.location.page_number
                if number is None or not 0 <= number < document.page_count:
                    continue
                page = document[number]
                if not match.location.ocr_words and number not in page_blocks:
                    page_blocks[number] = page.get_text("rawdict", sort=True)["blocks"]
                rects = (
                    _ocr_rects(match) if match.location.ocr_words
                    else _text_rects(page_blocks[number], match)
                )
                if not rects:
                    continue
                for rect in rects:
                    page.add_redact_annot(rect, fill=(1, 1, 0.55), cross_out=False)
                # One centred label on the widest line of a multiline entity.
                replacements[number].append(
                    (max(rects, key=lambda r: r.width), display_label(match, style))
                )
                match.applied = True
        font_path = _cyrillic_font_path() if replacements and style != LabelStyle.NONE else None
        font = fitz.Font(fontfile=str(font_path)) if font_path else None
        for number, labels in replacements.items():
            page = document[number]
            page.apply_redactions(graphics=0)
            for rect, label in labels:
                if font is not None:
                    _draw_label(page, rect, label, font, font_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        document.save(target, garbage=4, deflate=True)
    return target
