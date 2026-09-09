"""Детерминированный поиск структурированных сущностей в тексте."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from re import Pattern

from core.models import EntitySpan, EntityType

_SEPARATOR = r"[ \t]*(?::|№)?[ \t]*"
_VALUE_BOUNDARY_START = r"(?<!\d)"
_VALUE_BOUNDARY_END = r"(?!\d)"

_INN_PATTERNS = (
    re.compile(
        rf"\bИНН[ \t]*/[ \t]*КПП\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}(?:\d{{12}}|\d{{10}}){_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bИНН\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}(?:\d{{12}}|\d{{10}}){_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_KPP_PATTERNS = (
    re.compile(
        rf"\bИНН[ \t]*/[ \t]*КПП\b{_SEPARATOR}"
        rf"(?:\d{{12}}|\d{{10}})[ \t]*/[ \t]*"
        rf"(?P<value>(?<![0-9A-ZА-ЯЁ])\d{{4}}[0-9A-ZА-ЯЁ]{{2}}\d{{3}}"
        rf"(?![0-9A-ZА-ЯЁ]))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bКПП\b{_SEPARATOR}"
        rf"(?P<value>(?<![0-9A-ZА-ЯЁ])\d{{4}}[0-9A-ZА-ЯЁ]{{2}}\d{{3}}"
        rf"(?![0-9A-ZА-ЯЁ]))",
        re.IGNORECASE,
    ),
)

_OGRN_PATTERNS = (
    re.compile(
        rf"\bОГРНИП\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}\d{{15}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bОГРН(?!ИП)\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}\d{{13}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_PHONE_PATTERNS = (
    re.compile(
        r"\b(?:телефон|тел\.?|моб\.?)"
        r"[ \t]*(?::|-)?[ \t]*"
        r"(?P<value>(?<!\d)(?:\+7|8)?[ \t]*"
        r"(?:\(\d{3}\)|\d{3})[ \t-]*\d{3}[ \t-]*\d{2}[ \t-]*\d{2}(?!\d))",
        re.IGNORECASE,
    ),
)

_EMAIL_PATTERNS = (
    re.compile(
        r"(?<![\w.+-])(?P<value>"
        r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
        r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
        r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+"
        r")(?![\w-])",
        re.IGNORECASE,
    ),
)

_BANK_ACCOUNT_PATTERNS = (
    re.compile(
        rf"(?:\bр[ \t]*[./][ \t]*с\b|\bрасч[её]тный[ \t]+сч[её]т\b)"
        rf"{_SEPARATOR}(?P<value>{_VALUE_BOUNDARY_START}\d{{20}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_BIK_PATTERNS = (
    re.compile(
        rf"\bБИК\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}\d{{9}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_CONTRACT_NUMBER_PATTERNS = (
    re.compile(
        r"\b(?:договор(?:а|у|ом|е)?|контракт(?:а|у|ом|е)?)\b"
        r"(?:[ \t]+[А-ЯЁа-яё-]+){0,4}[ \t]*"
        r"(?:№|N|номер)[ \t]*(?::|-)?[ \t]*"
        r"(?P<value>(?=[A-ZА-ЯЁ0-9./-]*\d)"
        r"[A-ZА-ЯЁ0-9](?:[A-ZА-ЯЁ0-9./-]*[A-ZА-ЯЁ0-9])?)"
        r"(?![\w./-])",
        re.IGNORECASE,
    ),
)


def _is_valid_inn(value: str) -> bool:
    if len(value) == 10:
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        checksum = sum(int(digit) * weight for digit, weight in zip(value, weights))
        return checksum % 11 % 10 == int(value[9])

    if len(value) == 12:
        first_weights = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        second_weights = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        first_checksum = (
            sum(int(digit) * weight for digit, weight in zip(value, first_weights))
            % 11
            % 10
        )
        second_checksum = (
            sum(int(digit) * weight for digit, weight in zip(value, second_weights))
            % 11
            % 10
        )
        return first_checksum == int(value[10]) and second_checksum == int(value[11])

    return False


def _is_valid_ogrn(value: str) -> bool:
    if len(value) == 13:
        return int(value[:12]) % 11 % 10 == int(value[12])
    if len(value) == 15:
        return int(value[:14]) % 13 % 10 == int(value[14])
    return False


def _is_valid_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) == 10 or (len(digits) == 11 and digits[0] in "78")


def _always_valid(_: str) -> bool:
    return True


def _find_spans(
    text: str,
    entity_type: EntityType,
    patterns: Sequence[Pattern[str]],
    validator: Callable[[str], bool] = _always_valid,
) -> list[EntitySpan]:
    spans: list[EntitySpan] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group("value")
            if not validator(value):
                continue
            start, end = match.span("value")
            spans.append(
                EntitySpan(
                    entity_type=entity_type,
                    text=value,
                    start=start,
                    end=end,
                    source="rule",
                    confidence=1.0,
                )
            )
    return spans


_DETECTORS: dict[
    EntityType,
    tuple[Sequence[Pattern[str]], Callable[[str], bool]],
] = {
    EntityType.INN: (_INN_PATTERNS, _is_valid_inn),
    EntityType.KPP: (_KPP_PATTERNS, _always_valid),
    EntityType.OGRN: (_OGRN_PATTERNS, _is_valid_ogrn),
    EntityType.PHONE: (_PHONE_PATTERNS, _is_valid_phone),
    EntityType.EMAIL: (_EMAIL_PATTERNS, _always_valid),
    EntityType.BANK_ACCOUNT: (_BANK_ACCOUNT_PATTERNS, _always_valid),
    EntityType.BIK: (_BIK_PATTERNS, _always_valid),
    EntityType.CONTRACT_NUMBER: (_CONTRACT_NUMBER_PATTERNS, _always_valid),
}


def detect_rule_based(
    text: str,
    requested_types: Sequence[EntityType],
) -> list[EntitySpan]:
    """Найти запрошенные структурированные сущности и вернуть точные смещения."""

    requested = set(requested_types)
    candidates: list[EntitySpan] = []
    for entity_type, (patterns, validator) in _DETECTORS.items():
        if entity_type in requested:
            candidates.extend(_find_spans(text, entity_type, patterns, validator))

    candidates.sort(
        key=lambda span: (span.start, -(span.end - span.start), span.entity_type.value)
    )

    result: list[EntitySpan] = []
    seen: set[tuple[EntityType, int, int]] = set()
    for candidate in candidates:
        key = (candidate.entity_type, candidate.start, candidate.end)
        if key in seen:
            continue
        if any(
            candidate.start < existing.end and existing.start < candidate.end
            for existing in result
        ):
            continue
        seen.add(key)
        result.append(candidate)

    return sorted(result, key=lambda span: (span.start, span.end, span.entity_type.value))
