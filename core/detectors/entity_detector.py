"""Объединение детерминированного и LLM-поиска сущностей."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from core.detectors.rule_based import detect_rule_based
from core.document_registry import build_document_registry
from core.models import (
    ENTITY_MARKER_PREFIXES,
    EntitySpan,
    EntityType,
    Match,
    TextBlock,
)
from llm.base import BaseLLMClient
from llm.http_utils import LLMContextLimitError
from llm.request_budget import LLMRequestBudgetError
from llm.structured import LLMTruncatedResponseError

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

HYBRID_FALLBACK_TYPES = frozenset(
    {EntityType.PERSON_NAME, EntityType.ORGANIZATION, EntityType.ADDRESS}
)

LLM_BASED_TYPES = frozenset(
    {
        EntityType.PERSON_NAME,
        EntityType.ORGANIZATION,
        EntityType.ADDRESS,
        EntityType.AMOUNT,
    }
)

LLM_MAX_CONCURRENCY = 1
LLM_FRAGMENT_OVERLAP = 512
LLM_MIN_FRAGMENT_CHARS = 2_000
LLM_MAX_ADAPTIVE_DEPTH = 8
LLM_MAX_REQUESTS_PER_JOB = 64
AUXILIARY_ORGANIZATION_TYPES = frozenset(
    {EntityType.ORGANIZATION, EntityType.INN, EntityType.KPP, EntityType.OGRN}
)


@dataclass(frozen=True, slots=True)
class _Candidate:
    span: EntitySpan
    is_rule_based: bool


@dataclass(frozen=True, slots=True)
class _LLMFragment:
    block: TextBlock
    original_block_id: str
    offset: int


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
    if not span.text.strip() or block_text[span.start : span.end] != span.text:
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


def _preferred_cut(text: str, start: int, hard_end: int) -> int:
    search_start = start + (hard_end - start) // 2
    candidates = (
        text.rfind("\n", search_start, hard_end),
        text.rfind(" ", search_start, hard_end),
    )
    boundary = max(candidates)
    return boundary + 1 if boundary >= search_start else hard_end


def _fragment_blocks(
    blocks: Sequence[TextBlock],
    max_chars: int,
) -> list[_LLMFragment]:
    fragments: list[_LLMFragment] = []
    for block_index, block in enumerate(blocks):
        if max_chars <= 0 or len(block.text) <= max_chars:
            fragments.append(_LLMFragment(block, block.block_id, 0))
            continue
        start = 0
        fragment_index = 0
        overlap = min(LLM_FRAGMENT_OVERLAP, max(0, max_chars // 4))
        while start < len(block.text):
            hard_end = min(len(block.text), start + max_chars)
            end = _preferred_cut(block.text, start, hard_end)
            fragment_text = block.text[start:end]
            fragments.append(
                _LLMFragment(
                    TextBlock(
                        block_id=f"llm-fragment:{block_index}:{fragment_index}",
                        text=fragment_text,
                        kind=block.kind,
                        location=block.location,
                    ),
                    block.block_id,
                    start,
                )
            )
            if end >= len(block.text):
                break
            start = max(start + 1, end - overlap)
            fragment_index += 1
    return fragments


def _llm_batches(
    fragments: Sequence[_LLMFragment],
    max_chars: int,
    max_blocks: int = 100,
    max_tokens: int = 0,
    token_estimator: Callable[[str], int] | None = None,
) -> list[list[_LLMFragment]]:
    if max_chars <= 0:
        return [[fragment] for fragment in fragments]
    batches: list[list[_LLMFragment]] = []
    current: list[_LLMFragment] = []
    current_chars = 0
    current_tokens = 0
    for fragment in fragments:
        block_chars = len(fragment.block.text)
        block_tokens = token_estimator(fragment.block.text) if token_estimator else 0
        if current and (
            current_chars + block_chars > max_chars
            or len(current) >= max_blocks
            or (max_tokens > 0 and current_tokens + block_tokens > max_tokens)
        ):
            batches.append(current)
            current = []
            current_chars = 0
            current_tokens = 0
        current.append(fragment)
        current_chars += block_chars
        current_tokens += block_tokens
    if current:
        batches.append(current)
    return batches


def _bisect_fragment(fragment: _LLMFragment) -> tuple[_LLMFragment, _LLMFragment] | None:
    text = fragment.block.text
    if len(text) <= LLM_MIN_FRAGMENT_CHARS:
        return None
    midpoint = len(text) // 2
    split = _preferred_cut(text, 0, midpoint)
    left_end = min(len(text), split + LLM_FRAGMENT_OVERLAP)
    right_start = max(0, split - LLM_FRAGMENT_OVERLAP)
    if left_end >= len(text) or right_start <= 0:
        left_end = midpoint
        right_start = midpoint
    left = _LLMFragment(
        TextBlock(
            block_id=f"{fragment.block.block_id}:left",
            text=text[:left_end],
            kind=fragment.block.kind,
            location=fragment.block.location,
        ),
        fragment.original_block_id,
        fragment.offset,
    )
    right = _LLMFragment(
        TextBlock(
            block_id=f"{fragment.block.block_id}:right",
            text=text[right_start:],
            kind=fragment.block.kind,
            location=fragment.block.location,
        ),
        fragment.original_block_id,
        fragment.offset + right_start,
    )
    return left, right


def _split_failed_batch(
    batch: list[_LLMFragment],
) -> tuple[list[_LLMFragment], list[_LLMFragment]] | None:
    if len(batch) > 1:
        midpoint = len(batch) // 2
        return batch[:midpoint], batch[midpoint:]
    divided = _bisect_fragment(batch[0])
    return ([divided[0]], [divided[1]]) if divided else None


async def _find_llm_entities_adaptively(
    fragments: Sequence[_LLMFragment],
    mask_types: Sequence[EntityType],
    auxiliary_types: Sequence[EntityType],
    llm_client: BaseLLMClient,
    cancel_check: Callable[[], None] | None,
) -> dict[str, list[EntitySpan]]:
    pending: list[tuple[list[_LLMFragment], int]] = [
        (batch, 0)
        for batch in reversed(_llm_batches(
            fragments,
            llm_client.batch_max_chars,
            llm_client.batch_max_blocks,
            llm_client.batch_input_token_limit,
            llm_client.estimate_input_tokens,
        ))
    ]
    result: defaultdict[str, list[EntitySpan]] = defaultdict(list)
    seen: set[tuple[str, EntityType, int, int]] = set()
    request_count = 0
    while pending:
        if cancel_check is not None:
            cancel_check()
        batch, depth = pending.pop()
        if request_count >= LLM_MAX_REQUESTS_PER_JOB:
            raise LLMRequestBudgetError("LLM request budget exceeded")
        request_count += 1
        try:
            spans_by_fragment = await llm_client.find_entities_for_analysis(
                [fragment.block for fragment in batch],
                mask_types,
                auxiliary_types,
            )
        except (LLMContextLimitError, LLMTruncatedResponseError):
            split = (
                _split_failed_batch(batch)
                if depth < LLM_MAX_ADAPTIVE_DEPTH
                else None
            )
            if split is None:
                raise
            left, right = split
            pending.append((right, depth + 1))
            pending.append((left, depth + 1))
            continue
        for fragment in batch:
            for span in spans_by_fragment.get(fragment.block.block_id, ()):
                start = fragment.offset + span.start
                end = fragment.offset + span.end
                identity = (fragment.original_block_id, span.entity_type, start, end)
                if identity in seen:
                    continue
                seen.add(identity)
                result[fragment.original_block_id].append(
                    EntitySpan(
                        entity_type=span.entity_type,
                        text=span.text,
                        start=start,
                        end=end,
                        source=span.source,
                        confidence=span.confidence,
                        party_role=span.party_role,
                    )
                )
    for spans in result.values():
        spans.sort(key=lambda span: (span.start, span.end, span.entity_type.value))
    return dict(result)


async def detect_all(
    blocks: list[TextBlock],
    requested_types: Sequence[EntityType],
    llm_client: BaseLLMClient,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, list[Match]]:
    """Найти сущности во всех блоках и подготовить команды замены."""

    mask_types = tuple(dict.fromkeys(requested_types))
    requested = set(mask_types)
    analysis = set(requested)
    if EntityType.ORGANIZATION in requested or EntityType.PERSON_NAME in requested:
        analysis.update(AUXILIARY_ORGANIZATION_TYPES)
    analysis_types = tuple(entity_type for entity_type in EntityType if entity_type in analysis)
    rule_types = _ordered_types(analysis_types, RULE_BASED_TYPES)
    hybrid_types = _ordered_types(analysis_types, HYBRID_FALLBACK_TYPES)
    llm_types = _ordered_types(analysis_types, LLM_BASED_TYPES)
    llm_mask_types = _ordered_types(mask_types, LLM_BASED_TYPES)
    llm_auxiliary_types = tuple(item for item in llm_types if item not in llm_mask_types)

    candidates_by_index: list[list[_Candidate]] = []
    fallback_by_index: list[list[EntitySpan]] = []
    for block in blocks:
        rule_spans = detect_rule_based(block.text, rule_types)
        fallback_by_index.append(
            [
                span
                for span in detect_rule_based(block.text, hybrid_types)
                if _is_valid_span(span, block.text, analysis)
            ]
        )
        candidates_by_index.append(
            [
                _Candidate(span=span, is_rule_based=True)
                for span in rule_spans
                if _is_valid_span(span, block.text, analysis)
            ]
        )

    if llm_types:
        nonempty = [block for block in blocks if block.text.strip()]
        fragments = _fragment_blocks(nonempty, llm_client.batch_max_chars)
        if fragments:
            llm_results = await _find_llm_entities_adaptively(
                fragments,
                llm_mask_types,
                llm_auxiliary_types,
                llm_client,
                cancel_check,
            )
            if cancel_check is not None:
                cancel_check()
            allowed_llm_types = set(llm_types)
            block_indexes = {block.block_id: index for index, block in enumerate(blocks)}
            for block_id, spans in llm_results.items():
                index = block_indexes.get(block_id)
                if index is None:
                    continue
                block = blocks[index]
                candidates_by_index[index].extend(
                    _Candidate(span=span, is_rule_based=False)
                    for span in spans
                    if _is_valid_span(span, block.text, allowed_llm_types)
                )

    # Explicitly labelled heuristics are fallbacks: any overlapping LLM span keeps
    # its richer role metadata and confidence.
    for candidates, fallback_spans in zip(candidates_by_index, fallback_by_index):
        for span in fallback_spans:
            if not any(_overlaps(span, candidate.span) for candidate in candidates):
                candidates.append(_Candidate(span=span, is_rule_based=False))

    resolved_by_index = [
        _resolve_overlaps(candidates) for candidates in candidates_by_index
    ]

    spans_by_block = {
        block.block_id: spans for block, spans in zip(blocks, resolved_by_index)
    }
    registry = build_document_registry(blocks, spans_by_block)
    organization_records = {item.entity_id: item for item in registry.organizations}

    replacements: dict[tuple[EntityType, str], str] = {}
    counters: defaultdict[EntityType, int] = defaultdict(int)
    result: dict[str, list[Match]] = {}

    for block, spans in zip(blocks, resolved_by_index):
        block_matches: list[Match] = []
        for span in spans:
            if span.entity_type not in requested:
                continue
            mention_key = (block.block_id, span.entity_type, span.start, span.end)
            entity_id = registry.mention_entities.get(mention_key)
            replacement_key = (span.entity_type, entity_id or span.text)
            replacement = replacements.get(replacement_key)
            if replacement is None:
                counters[span.entity_type] += 1
                replacement = (
                    f"[{ENTITY_MARKER_PREFIXES[span.entity_type]}_{counters[span.entity_type]}]"
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
                    party_role=(
                        organization_records[entity_id].role
                        if entity_id in organization_records
                        else span.party_role
                    ),
                    entity_id=entity_id,
                    organization_id=registry.person_organizations.get(mention_key),
                    evidence=(
                        organization_records[entity_id].evidence
                        if entity_id in organization_records
                        else tuple(
                            relation_evidence
                            for relation in registry.relations
                            if relation.subject_id == entity_id
                            for relation_evidence in relation.evidence
                        )
                    ),
                    conflict=(
                        organization_records[entity_id].conflict
                        if entity_id in organization_records
                        else False
                    ),
                )
            )
        result[block.block_id] = block_matches

    return result
