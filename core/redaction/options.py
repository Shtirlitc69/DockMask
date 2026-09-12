"""Presentation choices; report identifiers remain stable in every mode."""

from enum import Enum

from core.models import ENTITY_MARKER_PREFIXES, EntityType, Match


class LabelStyle(str, Enum):
    FULL = "full"
    SHORT = "short"
    NONE = "none"


SHORT_PREFIXES = {
    EntityType.ORGANIZATION: "ОРГ",
    EntityType.PHONE: "ТЕЛ",
    EntityType.EMAIL: "ПОЧТА",
    EntityType.BANK_ACCOUNT: "СЧЁТ",
    EntityType.CONTRACT_NUMBER: "ДОГ",
}


def display_label(match: Match, style: LabelStyle | str = LabelStyle.FULL) -> str:
    return format_label(match.replacement, match.entity_type, style)


def format_label(replacement: str, entity_type: EntityType, style: LabelStyle | str) -> str:
    style = LabelStyle(style)
    if style == LabelStyle.NONE:
        return ""
    if style == LabelStyle.SHORT:
        prefix = ENTITY_MARKER_PREFIXES[entity_type]
        return replacement.replace(prefix, SHORT_PREFIXES.get(entity_type, prefix), 1)
    return replacement
