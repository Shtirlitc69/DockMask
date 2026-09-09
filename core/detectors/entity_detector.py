"""Объединение детерминированного и LLM-поиска сущностей."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from core.detectors.rule_based import detect_rule_based
from core.models import EntitySpan, EntityType, Match, TextBlock
from llm.base import BaseLLMClient

RULE_BASED_TYPES = frozenset(
    {
        EntityType.INN,
        EntityType.KPP,
        EntityType.OGRN,
        EntityType.PHONE,
        EntityType.EMAIL,
        EntityType.BANK_ACCOUNT,
        EntityType.BIK,
        EntityType.CONTRACT_NUMBER,
    }
)

LLM_BASED_TYPES = frozenset(
    {
        EntityType.PERSON_NAME,
        EntityType.ORGANIZATION,
        EntityType.ADDRESS,
        EntityType.AMOUNT,
    }
)

LLM_MAX_CONCURRENCY = 4


@dataclass(frozen=True, slots=True)
class _Candidate:
    span: EntitySpan
    is_rule_based: bool


def _ordered_types(
    requested_types: Sequence[EntityType],
    supported_types: frozenset[EntityType],
) -> tuple[EntityType, ...]:
    requested = set(requested_types)
    return tuple(entity_type for entity_type in EntityType if entity_type in requested & supported_types)


def _is_valid_span(
    span: EntitySpan,
    block_text: str,
    allowed_types: set[EntityType],
) -> bool:
    if not isinstance(span, EntitySpan) or span.entity_type not in allowed_types:
        return False
    if not isinstance(span.start, int) or not isinstance(span.end, int):
        return False
    if not 0 <= span.start < span.end <= len(block_text):
        return False
    if not span.text or block_text[span.start : span.end] != span.text:
        return False
    return 0.0 <= span.confidence <= 1.0


def _priority(candidate: _Candidate) -> tuple[object, ...]:
    span = candidate.span
    length = span.end - span.start
    if candidate.is_rule_based:
        return (0, -length, span.start, span.end, span.entity_type.value, span.text)
    return (
        1,
        -span.confidence,
        -length,
        span.start,
        span.end,
        span.entity_type.value,
        span.text,
        span.source,
    )


def _overlaps(left: EntitySpan, right: EntitySpan) -> bool:
    return left.start < right.end and right.start < left.end


def _resolve_overlaps(candidates: Sequence[_Candidate]) -> list[EntitySpan]:
    selected: list[EntitySpan] = []
    seen: set[tuple[EntityType, str, int, int]] = set()

    for candidate in sorted(candidates, key=_priority):
        span = candidate.span
        identity = (span.entity_type, span.text, span.start, span.end)
        if identity in seen:
            continue
        if any(_overlaps(span, existing) for existing in selected):
            continue
        seen.add(identity)
        selected.append(span)

    return sorted(selected, key=lambda span: (span.start, span.end, span.entity_type.value))


async def _find_llm_entities(
    block: TextBlock,
    llm_types: Sequence[EntityType],
    llm_client: BaseLLMClient,
    semaphore: asyncio.Semaphore,
) -> list[EntitySpan]:
    async with semaphore:
        return await llm_client.find_entities(block.text, llm_types)


async def detect_all(
    blocks: list[TextBlock],
    requested_types: Sequence[EntityType],
    llm_client: BaseLLMClient,
) -> dict[str, list[Match]]:
    """Найти сущности во всех блоках и подготовить команды замены."""

    requested = set(requested_types)
    rule_types = _ordered_types(requested_types, RULE_BASED_TYPES)
    llm_types = _ordered_types(requested_types, LLM_BASED_TYPES)

    candidates_by_index: list[list[_Candidate]] = []
    for block in blocks:
        rule_spans = detect_rule_based(block.text, rule_types)
        candidates_by_index.append(
            [
                _Candidate(span=span, is_rule_based=True)
                for span in rule_spans
                if _is_valid_span(span, block.text, requested)
            ]
        )

    if llm_types:
        semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENCY)
        llm_jobs = [
            (index, _find_llm_entities(block, llm_types, llm_client, semaphore))
            for index, block in enumerate(blocks)
            if block.text.strip()
        ]
        if llm_jobs:
            llm_results = await asyncio.gather(*(job for _, job in llm_jobs))
            allowed_llm_types = set(llm_types)
            for (index, _), spans in zip(llm_jobs, llm_results):
                block = blocks[index]
                candidates_by_index[index].extend(
                    _Candidate(span=span, is_rule_based=False)
                    for span in spans
                    if _is_valid_span(span, block.text, allowed_llm_types)
                )

    resolved_by_index = [
        _resolve_overlaps(candidates) for candidates in candidates_by_index
    ]

    replacements: dict[tuple[EntityType, str], str] = {}
    counters: defaultdict[EntityType, int] = defaultdict(int)
    result: dict[str, list[Match]] = {}

    for block, spans in zip(blocks, resolved_by_index):
        block_matches: list[Match] = []
        for span in spans:
            replacement_key = (span.entity_type, span.text)
            replacement = replacements.get(replacement_key)
            if replacement is None:
                counters[span.entity_type] += 1
                replacement = (
                    f"[{span.entity_type.value.upper()}_{counters[span.entity_type]}]"
                )
                replacements[replacement_key] = replacement

            block_matches.append(
                Match(
                    block_id=block.block_id,
                    entity_type=span.entity_type,
                    text=span.text,
                    start=span.start,
                    end=span.end,
                    replacement=replacement,
                    source=span.source,
                    confidence=span.confidence,
                    location=block.location,
                )
            )
        result[block.block_id] = block_matches

    return result
