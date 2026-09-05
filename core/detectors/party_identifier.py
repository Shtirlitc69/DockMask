"""Identify supplier and buyer matches from document context."""

from __future__ import annotations

import re

from core.models import EntityType, Match, PartyRole, TextBlock
from llm.base import BaseLLMClient


_PARTY_ENTITY_TYPES = frozenset(
    {EntityType.ORGANIZATION, EntityType.PERSON_NAME}
)
_SUPPLIER_PATTERN = re.compile(
    r"(?<!\w)(?:поставщик|исполнитель|подрядчик)(?!\w)",
    re.IGNORECASE,
)
_BUYER_PATTERN = re.compile(
    r"(?<!\w)(?:покупатель|заказчик)(?!\w)",
    re.IGNORECASE,
)


def _local_role(text: str) -> tuple[PartyRole, bool]:
    """Return the role and whether the text contains any local evidence."""

    has_supplier = _SUPPLIER_PATTERN.search(text) is not None
    has_buyer = _BUYER_PATTERN.search(text) is not None

    if has_supplier and not has_buyer:
        return PartyRole.SUPPLIER, True
    if has_buyer and not has_supplier:
        return PartyRole.BUYER, True
    return PartyRole.UNKNOWN, has_supplier or has_buyer


def _context(blocks: list[TextBlock], index: int) -> str:
    start = max(0, index - 1)
    end = min(len(blocks), index + 2)
    return "\n".join(block.text for block in blocks[start:end])


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

        local_role, has_local_evidence = _local_role(block.text)
        if not has_local_evidence:
            neighbor_texts: list[str] = []
            if index > 0:
                neighbor_texts.append(blocks[index - 1].text)
            if index + 1 < len(blocks):
                neighbor_texts.append(blocks[index + 1].text)
            neighbor_text = "\n".join(neighbor_texts)
            local_role, has_local_evidence = _local_role(neighbor_text)

        context_snippet: str | None = None
        for match in matches:
            if (
                match.entity_type not in _PARTY_ENTITY_TYPES
                or match.party_role is not PartyRole.UNKNOWN
            ):
                continue

            if has_local_evidence:
                match.party_role = local_role
                continue

            if context_snippet is None:
                context_snippet = _context(blocks, index)
            llm_role = await llm_client.classify_party(
                context_snippet,
                match.text,
            )
            if llm_role in (PartyRole.SUPPLIER, PartyRole.BUYER):
                match.party_role = llm_role

    return matches_by_block
