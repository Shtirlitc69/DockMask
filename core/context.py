"""Structural context for analysis; original text and redaction locations stay intact."""

import re
from dataclasses import asdict

from core.models import TextBlock


def enrich_context(blocks: list[TextBlock]) -> None:
    headers: dict[tuple, str] = {}
    section = ""
    for order, block in enumerate(blocks):
        loc = block.location
        if loc.table_index is not None:
            key = (loc.table_index, loc.column)
            if loc.row == 0:
                headers[key] = block.text
            block.context.setdefault("column_header", headers.get(key, ""))
        if re.match(r"^\d+\.\s+[А-ЯЁ ]{4,}$", block.text.strip()):
            section = block.text.strip()
        block.context.update(
            {
                "order": order,
                "section": section,
                "kind": block.kind.value,
                "location": {
                    k: v for k, v in asdict(loc).items() if v is not None and k != "ocr_words"
                },
            }
        )


def monetary_column(block: TextBlock) -> bool:
    return bool(
        re.search(
            r"\b(?:цена|сумма|стоимость)\b",
            str(block.context.get("column_header", "")),
            re.IGNORECASE,
        )
    )
