"""Shared structured-output behavior for all LLM providers."""

from __future__ import annotations

import logging
import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from core.models import EntitySpan, EntityType, PartyRole, TextBlock
from llm.base import BaseLLMClient
from llm.prompts import (
    BATCH_ENTITY_SYSTEM_PROMPT,
    ENTITY_SYSTEM_PROMPT,
    PARTY_SYSTEM_PROMPT,
    ROLE_RESPONSE_SCHEMA,
    block_entity_response_schema,
    build_block_entity_prompt,
    build_entity_prompt,
    build_party_prompt,
    entity_response_schema,
)

LOGGER = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class LLMResponseError(RuntimeError):
    """A provider response did not satisfy the structured-output contract."""

    category = "invalid_response"


class LLMTruncatedResponseError(LLMResponseError):
    """Generation reached its output limit; a smaller batch may help."""

    category = "response_truncated"


class LLMFilteredResponseError(LLMResponseError):
    """Provider filtering prevented complete processing; do not retry."""

    category = "response_filtered"


class EntityItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: str
    text: str
    party_role: Literal["supplier", "buyer", "unknown"] = "unknown"


class EntitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entities: list[EntityItem]


class BlockEntityItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    block_id: int
    type: str
    text: str
    party_role: Literal["supplier", "buyer", "unknown"]


class BlockEntitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    entities: list[BlockEntityItem]


class RoleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["supplier", "buyer", "unknown"]


# Backwards-compatible names kept for adapters and third-party callers.
entity_schema = entity_response_schema
ROLE_SCHEMA = ROLE_RESPONSE_SCHEMA


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
        LOGGER.warning("llm_validation category=invalid_structured_json")
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
        # Models may replace a PDF line wrap with a space. Locate only whitespace
        # variants and retain original characters and offsets, never fuzzy names.
        parts = entity.text.split()
        pattern = r"\s+".join(re.escape(part) for part in parts)
        if not pattern:
            continue
        if entity.text[0].isalnum():
            pattern = r"(?<!\w)" + pattern
        if entity.text[-1].isalnum():
            pattern += r"(?!\w)"
        matches = tuple(re.finditer(pattern, source_text))
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
                    party_role=PartyRole(entity.party_role),
                )
            )
    return sorted(spans, key=lambda span: (span.start, span.end, span.entity_type.value))


class StructuredLLMClient(BaseLLMClient):
    """Base implementation shared by JSON-capable provider transports."""

    source = "llm"
    confidence = 0.8
    batch_max_chars = 24_000
    batch_input_token_limit = 12_000
    batch_max_concurrency = 1
    provides_inline_roles = True

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        requested = frozenset(types)
        if not text or not requested:
            return []
        content = await self._complete(
            build_entity_prompt(text, requested),
            entity_response_schema(requested),
            system_prompt=ENTITY_SYSTEM_PROMPT,
        )
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
        content = await self._complete(
            build_party_prompt(context_snippet, candidate_name),
            ROLE_RESPONSE_SCHEMA,
            system_prompt=PARTY_SYSTEM_PROMPT,
        )
        role = PartyRole(parse_model_json(content, RoleResponse).role)
        return None if role is PartyRole.UNKNOWN else role

    async def find_entities_in_blocks(
        self,
        blocks: Sequence[TextBlock],
        types: Sequence[EntityType],
    ) -> dict[str, list[EntitySpan]]:
        requested = frozenset(types)
        result = {block.block_id: [] for block in blocks}
        if not blocks or not requested:
            return result

        indexed = list(enumerate(blocks))
        content = await self._complete(
            build_block_entity_prompt(
                [(index, block.text) for index, block in indexed],
                requested,
            ),
            block_entity_response_schema(
                [index for index, _ in indexed],
                requested,
            ),
            system_prompt=BATCH_ENTITY_SYSTEM_PROMPT,
        )
        payload = parse_model_json(content, BlockEntitiesResponse)
        by_index = {index: block for index, block in indexed}
        seen: set[tuple[int, EntityType, int, int]] = set()
        for entity in payload.entities:
            block = by_index.get(entity.block_id)
            if block is None:
                LOGGER.warning("LLM returned an unknown block id")
                continue
            try:
                entity_type = EntityType(entity.type)
            except ValueError:
                LOGGER.warning("LLM returned an unknown entity type")
                continue
            if entity_type not in requested or not entity.text:
                LOGGER.warning("LLM returned an invalid batch entity")
                continue
            for span in to_entity_spans(
                block.text, frozenset(requested),
                [EntityItem(type=entity.type, text=entity.text, party_role=entity.party_role)],
                source=self.source, confidence=self.confidence,
            ):
                identity = (entity.block_id, span.entity_type, span.start, span.end)
                if identity not in seen:
                    seen.add(identity)
                    result[block.block_id].append(span)
        for spans in result.values():
            spans.sort(key=lambda span: (span.start, span.end, span.entity_type.value))
        return result

    async def find_entities_for_analysis(
        self,
        blocks: Sequence[TextBlock],
        mask_types: Sequence[EntityType],
        auxiliary_types: Sequence[EntityType],
    ) -> dict[str, list[EntitySpan]]:
        requested = tuple(dict.fromkeys((*mask_types, *auxiliary_types)))
        selected = frozenset(requested)
        result = {block.block_id: [] for block in blocks}
        if not blocks or not selected:
            return result
        indexed = list(enumerate(blocks))
        content = await self._complete(
            build_block_entity_prompt(
                [(index, block.text) for index, block in indexed],
                selected,
                mask_types=mask_types,
                auxiliary_types=auxiliary_types,
            ),
            block_entity_response_schema([index for index, _ in indexed], selected),
            system_prompt=BATCH_ENTITY_SYSTEM_PROMPT,
        )
        payload = parse_model_json(content, BlockEntitiesResponse)
        by_index = {index: block for index, block in indexed}
        seen: set[tuple[int, EntityType, int, int]] = set()
        for entity in payload.entities:
            block = by_index.get(entity.block_id)
            try:
                entity_type = EntityType(entity.type)
            except ValueError:
                continue
            if block is None or entity_type not in selected or not entity.text:
                continue
            for span in to_entity_spans(
                block.text, frozenset(requested),
                [EntityItem(type=entity.type, text=entity.text, party_role=entity.party_role)],
                source=self.source, confidence=self.confidence,
            ):
                identity = (entity.block_id, span.entity_type, span.start, span.end)
                if identity not in seen:
                    seen.add(identity)
                    result[block.block_id].append(span)
        for spans in result.values():
            spans.sort(key=lambda span: (span.start, span.end, span.entity_type.value))
        return result

    @abstractmethod
    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
        *,
        system_prompt: str | None = None,
    ) -> str:
        """Return the provider's text content for a structured request."""
