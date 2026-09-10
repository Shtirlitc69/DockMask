"""Identify supplier and buyer matches from document context."""

from __future__ import annotations

import re

from core.models import EntityType, Match, PartyRole, TextBlock
from llm.base import BaseLLMClient

_PARTY_ENTITY_TYPES = frozenset(
    {EntityType.ORGANIZATION, EntityType.PERSON_NAME}
)
_SUPPLIER_PATTERN = re.compile(
    r"(?<!\w)(?:поставщик|исполнитель|подрядчик|продавец)(?!\w)",
    re.IGNORECASE,
)
_BUYER_PATTERN = re.compile(
    r"(?<!\w)(?:покупатель|заказчик|клиент)(?!\w)",
    re.IGNORECASE,
)


def _marker_distance(marker: re.Match[str], start: int, end: int) -> int:
    if marker.end() <= start:
        return start - marker.end()
    if marker.start() >= end:
        return marker.start() - end
    return 0


def _local_role(text: str, start: int, end: int) -> tuple[PartyRole, bool]:
    """Return the role of one candidate based on its nearest explicit marker."""

    left = max(text.rfind(separator, 0, start) for separator in (".", ";", "\n", "\r")) + 1
    right = min(
        (
            position
            for separator in (".", ";", "\n", "\r")
            if (position := text.find(separator, end)) >= 0
        ),
        default=len(text),
    )

    def collect(search_start: int, search_end: int) -> list[tuple[int, PartyRole]]:
        return [
            *(
                (_marker_distance(marker, start, end), PartyRole.SUPPLIER)
                for marker in _SUPPLIER_PATTERN.finditer(text, search_start, search_end)
            ),
            *(
                (_marker_distance(marker, start, end), PartyRole.BUYER)
                for marker in _BUYER_PATTERN.finditer(text, search_start, search_end)
            ),
        ]

    evidence = collect(left, right) or collect(0, len(text))
    if not evidence:
        return PartyRole.UNKNOWN, False
    nearest_distance = min(distance for distance, _ in evidence)
    nearest_roles = {
        role for distance, role in evidence if distance == nearest_distance
    }
    if len(nearest_roles) == 1:
        return nearest_roles.pop(), True
    return PartyRole.UNKNOWN, True


def _context(blocks: list[TextBlock], index: int, match: Match) -> tuple[str, int, int]:
    start = max(0, index - 1)
    end = min(len(blocks), index + 2)
    selected = blocks[start:end]
    prefix = sum(len(block.text) + 1 for block in selected[: index - start])
    return (
        "\n".join(block.text for block in selected),
        prefix + match.start,
        prefix + match.end,
    )


async def identify_parties(
    blocks: list[TextBlock],
    matches_by_block: dict[str, list[Match]],
    llm_client: BaseLLMClient,
) -> dict[str, list[Match]]:
    """Assign party roles in place, preferring deterministic local evidence."""

    for index, block in enumerate(blocks):
        matches = matches_by_block.get(block.block_id, ())
        if not matches:
            continue

        for match in matches:
            if match.entity_type not in _PARTY_ENTITY_TYPES:
                continue
            if match.party_role is not PartyRole.UNKNOWN:
                continue

            local_role, _ = _local_role(block.text, match.start, match.end)
            if local_role is not PartyRole.UNKNOWN:
                match.party_role = local_role
                continue

            context_snippet, context_start, context_end = _context(
                blocks, index, match
            )
            local_role, _ = _local_role(
                context_snippet, context_start, context_end
            )
            if local_role is not PartyRole.UNKNOWN:
                match.party_role = local_role
                continue

            llm_role = await llm_client.classify_party(
                context_snippet,
                match.text,
            )
            if llm_role in (PartyRole.SUPPLIER, PartyRole.BUYER):
                match.party_role = llm_role

    roles_by_entity: dict[tuple[EntityType, str], set[PartyRole]] = {}
    for match in (
        item for values in matches_by_block.values() for item in values
    ):
        if match.entity_type not in _PARTY_ENTITY_TYPES:
            continue
        if match.party_role is PartyRole.UNKNOWN:
            continue
        roles_by_entity.setdefault((match.entity_type, match.text), set()).add(
            match.party_role
        )
    for match in (
        item for values in matches_by_block.values() for item in values
    ):
        if match.party_role is not PartyRole.UNKNOWN:
            continue
        roles = roles_by_entity.get((match.entity_type, match.text), set())
        if len(roles) == 1:
            match.party_role = next(iter(roles))

    return matches_by_block
