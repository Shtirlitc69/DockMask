"""Versioned prompts and response schemas shared by every LLM adapter."""

from __future__ import annotations

from collections.abc import Collection

from core.models import EntityType

PROMPT_VERSION = "1.0.0"

ENTITY_SYSTEM_PROMPT = (
    "Ты извлекаешь конфиденциальные сущности из синтетического или пользовательского "
    "фрагмента документа. Возвращай только JSON по переданной схеме. Не исправляй и "
    "не нормализуй найденный текст: значение должно в точности присутствовать во входе."
)
ENTITY_USER_TEMPLATE = (
    "Запрошенные типы: {entity_types}.\n"
    "Найди только сущности этих типов.\n"
    "Исходный текст:\n{source_text}"
)

PARTY_SYSTEM_PROMPT = (
    "Определи роль указанной стороны только по данному контексту. Возвращай только JSON "
    "по переданной схеме. Если доказательств недостаточно, верни unknown."
)
PARTY_USER_TEMPLATE = "Сторона: {candidate_name}\nКонтекст:\n{context_snippet}"


def build_entity_prompt(text: str, requested: Collection[EntityType]) -> str:
    """Build the user message for exact entity extraction."""

    values = ", ".join(sorted(item.value for item in requested))
    return ENTITY_USER_TEMPLATE.format(entity_types=values, source_text=text)


def build_party_prompt(context_snippet: str, candidate_name: str) -> str:
    """Build the user message for party classification."""

    return PARTY_USER_TEMPLATE.format(
        candidate_name=candidate_name,
        context_snippet=context_snippet,
    )


def entity_response_schema(requested: Collection[EntityType]) -> dict[str, object]:
    """Return the strict JSON Schema for requested entity types."""

    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": sorted(item.value for item in requested),
                        },
                        "text": {"type": "string"},
                    },
                    "required": ["type", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entities"],
        "additionalProperties": False,
    }


ROLE_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "role": {
            "type": "string",
            "enum": ["supplier", "buyer", "unknown"],
        }
    },
    "required": ["role"],
    "additionalProperties": False,
}
