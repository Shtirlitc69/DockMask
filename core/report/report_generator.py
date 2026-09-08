"""Generate JSON report payloads for applied redactions."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from core.models import Match, PartyRole, ReportEntry


def _location_to_dict(location: Any) -> dict[str, Any]:
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
    }


class ReportGenerator:
    """Serialize redaction matches into a stable JSON report."""

    @staticmethod
    def build(matches: Iterable[Match]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for match in matches:
            entries.append(
                {
                    "entity_type": match.entity_type.value,
                    "original_value": match.text,
                    "replacement": match.replacement,
                    "location": _location_to_dict(match.location),
                    "source": match.source,
                    "confidence": match.confidence,
                    "party_role": match.party_role.value,
                    "applied": bool(match.applied),
                }
            )
        return entries

    @staticmethod
    def generate(matches: Iterable[Match]) -> list[dict[str, Any]]:
        return ReportGenerator.build(matches)

    @staticmethod
    def to_json(matches: Iterable[Match], *, indent: int = 2) -> str:
        return json.dumps(ReportGenerator.build(matches), ensure_ascii=False, indent=indent)

    @staticmethod
    def write_report(path: str | Path, matches: Iterable[Match]) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(ReportGenerator.to_json(matches), encoding="utf-8")
        return target


def generate_report(matches: Iterable[Match]) -> list[dict[str, Any]]:
    return ReportGenerator.generate(matches)


def build_report(matches: Iterable[Match]) -> list[dict[str, Any]]:
    return ReportGenerator.build(matches)


def write_report(path: str | Path, matches: Iterable[Match]) -> Path:
    return ReportGenerator.write_report(path, matches)
