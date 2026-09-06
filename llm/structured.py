"""Shared structured-output behavior for all LLM providers."""

from __future__ import annotations

import logging
import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from core.models import EntitySpan, EntityType, PartyRole
from llm.base import BaseLLMClient

LOGGER = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMResponseError(RuntimeError):
    """A provider response did not satisfy the structured-output contract."""


class EntityItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: str
    text: str


class EntitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entities: list[EntityItem]


class RoleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["supplier", "buyer", "unknown"]


def entity_schema(requested: frozenset[EntityType]) -> dict[str, object]:
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


ROLE_SCHEMA: dict[str, object] = {
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


def parse_model_json(content: str, model: type[ModelT]) -> ModelT:
    """Strip a complete Markdown fence and validate strict JSON."""

    stripped = content.strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```",
        stripped,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fenced:
        stripped = fenced.group(1)
    try:
        return model.model_validate_json(stripped)
    except ValidationError:
        raise LLMResponseError("Provider returned invalid structured JSON") from None


def to_entity_spans(
    source_text: str,
    requested: frozenset[EntityType],
    entities: Sequence[EntityItem],
    *,
    source: str,
    confidence: float = 0.8,
    logger: logging.Logger = LOGGER,
) -> list[EntitySpan]:
    """Locate exact entity values without trusting model-provided coordinates."""

    spans: list[EntitySpan] = []
    seen: set[tuple[EntityType, int, int]] = set()
    for entity in entities:
        try:
            entity_type = EntityType(entity.type)
        except ValueError:
            logger.warning("LLM returned an unknown entity type")
            continue
        if entity_type not in requested:
            logger.warning("LLM returned an unrequested entity type")
            continue
        if not entity.text:
            logger.warning("LLM returned an empty entity value for type %s", entity_type.value)
            continue
        matches = tuple(re.finditer(re.escape(entity.text), source_text))
        if not matches:
            logger.warning(
                "LLM entity value was absent from source text for type %s",
                entity_type.value,
            )
            continue
        for match in matches:
            key = (entity_type, match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            spans.append(
                EntitySpan(
                    entity_type=entity_type,
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    source=source,
                    confidence=confidence,
                )
            )
    return sorted(spans, key=lambda span: (span.start, span.end, span.entity_type.value))


class StructuredLLMClient(BaseLLMClient):
    """Base implementation shared by JSON-capable provider transports."""

    source = "llm"
    confidence = 0.8

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        requested = frozenset(types)
        if not text or not requested:
            return []
        type_values = ", ".join(sorted(item.value for item in requested))
        prompt = (
            "Извлеки из исходного текста только сущности запрошенных типов. "
            "Верни только JSON вида "
            '{"entities":[{"type":"person_name","text":"точный текст"}]}. '
            "Не меняй регистр, пробелы или пунктуацию значения. "
            f"Запрошенные типы: {type_values}.\nИсходный текст:\n{text}"
        )
        content = await self._complete(prompt, entity_schema(requested))
        payload = parse_model_json(content, EntitiesResponse)
        return to_entity_spans(
            text,
            requested,
            payload.entities,
            source=self.source,
            confidence=self.confidence,
        )

    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        if not context_snippet or not candidate_name:
            return None
        prompt = (
            "Определи роль указанной стороны только по контексту. "
            '{"role":"supplier"}, где role — supplier, buyer или unknown.\n'
            f"Сторона: {candidate_name}\nКонтекст:\n{context_snippet}"
        )
        content = await self._complete(prompt, ROLE_SCHEMA)
        role = PartyRole(parse_model_json(content, RoleResponse).role)
        return None if role is PartyRole.UNKNOWN else role

    @abstractmethod
    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        """Return the provider's text content for a structured request."""
