"""Deterministic offline implementation of the LLM provider contract.

The mock is intentionally small and predictable.  It exists to unblock the
pipeline and UI while a real provider is unavailable; it is not intended to
replace the rule-based detector or provide production-quality NER.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from core.models import EntitySpan, EntityType, PartyRole
from llm.base import BaseLLMClient


MOCK_SOURCE = "llm-mock"
MOCK_CONFIDENCE = 0.5


@dataclass(frozen=True, slots=True)
class _EntityPattern:
    entity_type: EntityType
    expression: re.Pattern[str]
    value_group: str | int = 0


_ENTITY_PATTERNS: tuple[_EntityPattern, ...] = (
    _EntityPattern(
        EntityType.PERSON_NAME,
        re.compile(
            r"(?<![\w-])(?:"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
            r"|[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+"
            r"[А-ЯЁ]\.\s*[А-ЯЁ]\."
            r")(?![\w-])"
        ),
    ),
    _EntityPattern(
        EntityType.ORGANIZATION,
        re.compile(
            r"(?<!\w)(?:ООО|ПАО|АО|ЗАО|ОАО|ИП)\s+"
            r"(?:«[^»\r\n]+»|\"[^\"\r\n]+\"|"
            r"[А-ЯЁ][\w.-]*(?:\s+[А-ЯЁ][\w.-]*){0,3})"
        ),
    ),
    _EntityPattern(
        EntityType.ADDRESS,
        re.compile(
            r"(?i)(?:юридический\s+|почтовый\s+)?адрес\s*:\s*"
            r"(?P<value>[^;\r\n]+)"
        ),
        "value",
    ),
    _EntityPattern(
        EntityType.AMOUNT,
        re.compile(
            r"(?<!\w)\d+(?:[ \u00a0]\d{3})*(?:[.,]\d{1,2})?"
            r"\s*(?:руб(?:л(?:ей|я|ь))?\.?|₽|RUB)(?!\w)",
            re.IGNORECASE,
        ),
    ),
)

_SUPPLIER_WORDS = ("поставщик", "исполнитель", "подрядчик", "продавец")
_BUYER_WORDS = ("покупатель", "заказчик", "клиент")


class MockLLMClient(BaseLLMClient):
    """Regex-backed provider for repeatable local development and tests."""

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        """Return exact spans for supported requested types in document order."""

        requested = set(types)
        spans: list[EntitySpan] = []

        for pattern in _ENTITY_PATTERNS:
            if pattern.entity_type not in requested:
                continue

            for match in pattern.expression.finditer(text):
                start, end = match.span(pattern.value_group)
                value = text[start:end]
                spans.append(
                    EntitySpan(
                        entity_type=pattern.entity_type,
                        text=value,
                        start=start,
                        end=end,
                        source=MOCK_SOURCE,
                        confidence=MOCK_CONFIDENCE,
                    )
                )

        return sorted(
            spans,
            key=lambda span: (span.start, span.end, span.entity_type.value),
        )

    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        """Classify a candidate by the nearest explicit role word."""

        context = context_snippet.casefold()
        candidate = candidate_name.strip().casefold()
        if not context or not candidate:
            return None

        candidate_start = context.find(candidate)
        if candidate_start < 0:
            return self._classify_without_candidate(context)

        candidate_end = candidate_start + len(candidate)
        clause = self._candidate_clause(context, candidate_start, candidate_end)
        clause_role = self._classify_without_candidate(clause)
        if clause_role is not None:
            return clause_role

        supplier_distance = self._nearest_distance(
            context,
            candidate_start,
            candidate_end,
            _SUPPLIER_WORDS,
        )
        buyer_distance = self._nearest_distance(
            context,
            candidate_start,
            candidate_end,
            _BUYER_WORDS,
        )

        if supplier_distance is None and buyer_distance is None:
            return None
        if buyer_distance is None:
            return PartyRole.SUPPLIER
        if supplier_distance is None:
            return PartyRole.BUYER
        if supplier_distance == buyer_distance:
            return None
        return (
            PartyRole.SUPPLIER
            if supplier_distance < buyer_distance
            else PartyRole.BUYER
        )

    @staticmethod
    def _candidate_clause(context: str, candidate_start: int, candidate_end: int) -> str:
        """Return the punctuation-delimited clause containing the candidate."""

        left_boundaries = (
            context.rfind(separator, 0, candidate_start)
            for separator in (".", ";", "\n", "\r")
        )
        left = max(left_boundaries) + 1

        right_boundaries = (
            position
            for separator in (".", ";", "\n", "\r")
            if (position := context.find(separator, candidate_end)) >= 0
        )
        right = min(right_boundaries, default=len(context))
        return context[left:right]

    @staticmethod
    def _classify_without_candidate(context: str) -> PartyRole | None:
        has_supplier = any(word in context for word in _SUPPLIER_WORDS)
        has_buyer = any(word in context for word in _BUYER_WORDS)
        if has_supplier == has_buyer:
            return None
        return PartyRole.SUPPLIER if has_supplier else PartyRole.BUYER

    @staticmethod
    def _nearest_distance(
        context: str,
        candidate_start: int,
        candidate_end: int,
        words: Iterable[str],
    ) -> int | None:
        distances: list[int] = []
        for word in words:
            for match in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", context):
                if match.end() <= candidate_start:
                    distances.append(candidate_start - match.end())
                elif match.start() >= candidate_end:
                    distances.append(match.start() - candidate_end)
                else:
                    distances.append(0)
        return min(distances) if distances else None
