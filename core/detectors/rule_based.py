"""Детерминированный поиск структурированных сущностей в тексте."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from re import Pattern

from core.models import EntitySpan, EntityType
from core.telemetry import record

_HSPACE = r"[ \t\r\n\u00a0\u202f]"
_SEPARATOR = rf"{_HSPACE}*(?::|№)?{_HSPACE}*"
_VALUE_BOUNDARY_START = r"(?<!\d)"
_VALUE_BOUNDARY_END = r"(?!\d)"
_DIGIT_GAP = r"[ \t\u00a0\u202f]*"

_INN_PATTERNS = (
    re.compile(
        rf"\bИНН[ \t]*/[ \t]*КПП\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}(?:\d(?:{_DIGIT_GAP}\d){{11}}|\d(?:{_DIGIT_GAP}\d){{9}}){_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bИНН\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}(?:\d(?:{_DIGIT_GAP}\d){{11}}|\d(?:{_DIGIT_GAP}\d){{9}}){_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_KPP_PATTERNS = (
    re.compile(
        rf"\bИНН[ \t]*/[ \t]*КПП\b{_SEPARATOR}"
        rf"(?:\d(?:{_DIGIT_GAP}\d){{11}}|\d(?:{_DIGIT_GAP}\d){{9}})[ \t]*/[ \t]*"
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
        rf"(?P<value>{_VALUE_BOUNDARY_START}\d(?:{_DIGIT_GAP}\d){{14}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bОГРН(?!ИП)\b{_SEPARATOR}"
        rf"(?P<value>{_VALUE_BOUNDARY_START}\d(?:{_DIGIT_GAP}\d){{12}}{_VALUE_BOUNDARY_END})",
        re.IGNORECASE,
    ),
)

_PHONE_PATTERNS = (
    re.compile(
        r"\b(?:телефон|тел\.?|моб\.?)"
        r"\s*(?::|-)?\s*"
        r"(?P<value>(?<!\d)(?:\+7|8)?\s*"
        r"(?:\(\d{3}\)|\d{3})[\s-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d))",
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
        rf"(?:\bл\s*[./]\s*с\b|\bлицевой\s+сч[её]т\b)"
        rf"{_SEPARATOR}(?P<value>(?<!\d)(?:\d{{20}}|\d{{11}})(?!\d))",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:\b[рк]\s*[./]\s*с\b|\b(?:расч[её]тный|корреспондентский)\s+сч[её]т\b)"
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
        rf"(?:{_HSPACE}+[А-ЯЁа-яё-]+){{0,4}}{_HSPACE}*"
        rf"(?:№|N|номер){_HSPACE}*(?::|-)?{_HSPACE}*"
        r"(?P<value>(?=[A-ZА-ЯЁ0-9./-]*\d)"
        r"[A-ZА-ЯЁ0-9](?:[A-ZА-ЯЁ0-9./-]*[A-ZА-ЯЁ0-9])?)"
        r"(?![\w./-])",
        re.IGNORECASE,
    ),
)

_PERSON_NAME_PATTERNS = (
    re.compile(
        r"(?P<value>\b[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]*(?:вич|вна|вича|вны))\b"
    ),
    re.compile(r"(?P<value>\b[А-ЯЁ][а-яё-]+[ \t]+[А-ЯЁ]\.[ \t]*[А-ЯЁ]\.)(?!\w)"),
    re.compile(r"(?P<value>(?<!\w)[А-ЯЁ]\.[ \t]*[А-ЯЁ]\.[ \t]*[А-ЯЁ][а-яё-]+\b)"),
    re.compile(
        r"(?:/\s*|(?:руководитель|директор|бухгалтер|ответственное лицо)\s*:?\s*)"
        r"(?P<value>[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)(?=\s*[/,;]|$)"
    ),
    re.compile(
        r"\bв\s+лице(?:\s+[а-яё-]+){0,5}\s+"
        r"(?P<value>[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)"
        r"(?=\s*[,;])",
        re.IGNORECASE,
    ),
)

_ORGANIZATION_PATTERNS = (
    re.compile(
        r"(?P<value>(?:Общество с ограниченной ответственностью|"
        r"Муниципальное бюджетное общеобразовательное учреждение|МБОУ|МБОУ СОШ)\s+"
        r"(?:«[^»\r\n]+»|СОШ\s*№\s*\d+|№\s*\d+)"
        r"(?:\s+г\.\s*[А-ЯЁ][а-яё-]+)?)"
    ),
    re.compile(
        r"(?P<value>(?<!\w)(?:ООО|ПАО|АО|ЗАО|ОАО|ИП)\s+"
        r"(?:«[^»\r\n]+»|\"[^\"\r\n]+\"|"
        r"[А-ЯЁ][\w.-]*(?:\s+[А-ЯЁ][\w.-]*){0,4}))"
    ),
    re.compile(
        r"(?P<value>(?<!\w)(?:ГАУ|ГБУ|МБУ|ФГБУ)(?:\s+[А-ЯЁ]{2,5})?\s+"
        r"(?:«[^»\r\n]+»|\"[^\"\r\n]+\"|"
        r"[А-ЯЁ][\w.-]*(?:\s+[А-ЯЁ][\w.-]*){0,4}))"
    ),
)

_ADDRESS_PATTERNS = (
    re.compile(
        r"(?P<value>(?<!\d)\d{6},\s*г\.\s*[А-ЯЁа-яё-]+,\s*"
        r"(?:ул\.|просп\.|пер\.|пр-т)\s*[^,;\r\n]+,\s*д\.\s*\d+[а-яёА-ЯЁ/-]*"
        r"(?:,\s*(?:стр\.|корп\.|кв\.|оф\.)\s*\d+[а-яёА-ЯЁ/-]*)*)"
    ),
    re.compile(
        r"(?:\bюридический\s+|\bпочтовый\s+|\bфактический\s+)?\bадрес\s*:\s*"
        r"(?P<value>[^;\r\n]{5,}(?:\r?\n(?:г\.|ул\.|просп\.|пер\.|д\.)[^;\r\n]+)?)",
        re.IGNORECASE,
    ),
)

_MONEY_NUMBER = r"\d{1,3}(?:[ \u00a0\u202f]\d{3})*(?:[,.]\d{2})?|\d+(?:[,.]\d{2})?"
_MONEY_WORD = (
    r"(?:ноль|один|одна|одно|одну|два|две|три|четыре|пять|шесть|семь|восемь|девять|"
    r"десять|одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|шестнадцать|"
    r"семнадцать|восемнадцать|девятнадцать|двадцать|тридцать|сорок|пятьдесят|"
    r"шестьдесят|семьдесят|восемьдесят|девяносто|сто|двести|триста|четыреста|"
    r"пятьсот|шестьсот|семьсот|восемьсот|девятьсот|тысяч[аиу]?|миллион(?:а|ов)?|миллиард(?:а|ов)?)"
)
_MONEY_WORDS = rf"{_MONEY_WORD}(?:\s+{_MONEY_WORD}){{0,20}}"
_AMOUNT_PATTERNS = (
    re.compile(
        rf"(?P<value>(?<![\w.,])(?:{_MONEY_NUMBER})(?:\s*\({_MONEY_WORDS}\))?"
        r"\s*(?:руб(?:\.|лей|ля|ль)?|₽|долларов|евро)(?:\s+\d{2}\s+коп(?:еек|ейки|ейка|\.)?)?)(?!\w)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<value>\b{_MONEY_WORDS}\s+руб(?:лей|ля|ль)(?:\s+\d{{2}}\s+копеек)?)",
        re.IGNORECASE,
    ),
)


def _is_valid_inn(value: str) -> bool:
    value = re.sub(r"\s", "", value)
    if len(value) == 10:
        weights = (2, 4, 10, 3, 5, 9, 4, 6, 8)
        checksum = sum(int(digit) * weight for digit, weight in zip(value, weights))
        return checksum % 11 % 10 == int(value[9])

    if len(value) == 12:
        first_weights = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        second_weights = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
        first_checksum = (
            sum(int(digit) * weight for digit, weight in zip(value, first_weights)) % 11 % 10
        )
        second_checksum = (
            sum(int(digit) * weight for digit, weight in zip(value, second_weights)) % 11 % 10
        )
        return first_checksum == int(value[10]) and second_checksum == int(value[11])

    return False


def _is_valid_ogrn(value: str) -> bool:
    value = re.sub(r"\s", "", value)
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
            if entity_type in {EntityType.INN, EntityType.OGRN}:
                record(
                    "identifier_validation",
                    entity_type=entity_type.value,
                    start=match.start("value"),
                    checksum_valid=(
                        _is_valid_inn(value)
                        if entity_type is EntityType.INN
                        else _is_valid_ogrn(value)
                    ),
                )
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
    EntityType.PERSON_NAME: (_PERSON_NAME_PATTERNS, _always_valid),
    EntityType.ORGANIZATION: (_ORGANIZATION_PATTERNS, _always_valid),
    EntityType.ADDRESS: (_ADDRESS_PATTERNS, _always_valid),
    EntityType.INN: (_INN_PATTERNS, _always_valid),
    EntityType.KPP: (_KPP_PATTERNS, _always_valid),
    EntityType.OGRN: (_OGRN_PATTERNS, _always_valid),
    EntityType.AMOUNT: (_AMOUNT_PATTERNS, _always_valid),
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

    candidates.sort(key=lambda span: (span.start, -(span.end - span.start), span.entity_type.value))

    result: list[EntitySpan] = []
    seen: set[tuple[EntityType, int, int]] = set()
    for candidate in candidates:
        key = (candidate.entity_type, candidate.start, candidate.end)
        if key in seen:
            continue
        if any(
            candidate.start < existing.end and existing.start < candidate.end for existing in result
        ):
            continue
        seen.add(key)
        result.append(candidate)

    return sorted(result, key=lambda span: (span.start, span.end, span.entity_type.value))
