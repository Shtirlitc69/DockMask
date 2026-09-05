"""Tests for deterministic and LLM-backed party identification."""

import unittest
from collections.abc import Sequence
from dataclasses import fields

from core.detectors.party_identifier import identify_parties
from core.models import (
    BlockKind,
    EntitySpan,
    EntityType,
    Location,
    Match,
    PartyRole,
    TextBlock,
)
from llm.base import BaseLLMClient


class PartyLLMClient(BaseLLMClient):
    def __init__(self, role: object = None) -> None:
        self.role = role
        self.calls: list[tuple[str, str]] = []

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        return []

    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        self.calls.append((context_snippet, candidate_name))
        return self.role  # type: ignore[return-value]


class PartyIdentifierTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def block(index: int, text: str) -> TextBlock:
        return TextBlock(
            block_id=f"p:{index}",
            text=text,
            kind=BlockKind.DOCX_PARAGRAPH,
            location=Location(paragraph_index=index),
        )

    @staticmethod
    def match(
        block: TextBlock,
        text: str,
        entity_type: EntityType = EntityType.ORGANIZATION,
        party_role: PartyRole = PartyRole.UNKNOWN,
    ) -> Match:
        start = block.text.index(text)
        return Match(
            block_id=block.block_id,
            entity_type=entity_type,
            text=text,
            start=start,
            end=start + len(text),
            replacement="[ENTITY_1]",
            source="test",
            confidence=0.9,
            location=block.location,
            party_role=party_role,
        )

    async def test_supplier_is_identified_locally_without_llm(self) -> None:
        block = self.block(0, "Поставщик: ООО Ромашка")
        match = self.match(block, "ООО Ромашка")
        client = PartyLLMClient(PartyRole.BUYER)

        result = await identify_parties(
            [block], {block.block_id: [match]}, client
        )

        self.assertEqual(match.party_role, PartyRole.SUPPLIER)
        self.assertEqual(client.calls, [])
        self.assertIs(result[block.block_id][0], match)

    async def test_role_can_be_taken_from_previous_block(self) -> None:
        heading = self.block(0, "Исполнитель")
        candidate = self.block(1, "ООО Ромашка")
        match = self.match(candidate, candidate.text)
        client = PartyLLMClient()

        await identify_parties(
            [heading, candidate], {candidate.block_id: [match]}, client
        )

        self.assertEqual(match.party_role, PartyRole.SUPPLIER)
        self.assertEqual(client.calls, [])

    async def test_current_blocks_distinguish_both_adjacent_parties(self) -> None:
        supplier = self.block(0, "Подрядчик: ООО Альфа")
        buyer = self.block(1, "Заказчик: АО Бета")
        supplier_match = self.match(supplier, "ООО Альфа")
        buyer_match = self.match(buyer, "АО Бета")
        client = PartyLLMClient()

        await identify_parties(
            [supplier, buyer],
            {
                supplier.block_id: [supplier_match],
                buyer.block_id: [buyer_match],
            },
            client,
        )

        self.assertEqual(supplier_match.party_role, PartyRole.SUPPLIER)
        self.assertEqual(buyer_match.party_role, PartyRole.BUYER)
        self.assertEqual(client.calls, [])

    async def test_conflicting_current_evidence_stays_unknown_without_llm(self) -> None:
        block = self.block(0, "Поставщик и покупатель: ООО Альфа")
        match = self.match(block, "ООО Альфа")
        client = PartyLLMClient(PartyRole.SUPPLIER)

        await identify_parties([block], {block.block_id: [match]}, client)

        self.assertEqual(match.party_role, PartyRole.UNKNOWN)
        self.assertEqual(client.calls, [])

    async def test_conflicting_neighbors_stay_unknown_without_llm(self) -> None:
        previous = self.block(0, "Поставщик")
        candidate = self.block(1, "ООО Альфа")
        following = self.block(2, "Покупатель")
        match = self.match(candidate, candidate.text)
        client = PartyLLMClient(PartyRole.SUPPLIER)

        await identify_parties(
            [previous, candidate, following],
            {candidate.block_id: [match]},
            client,
        )

        self.assertEqual(match.party_role, PartyRole.UNKNOWN)
        self.assertEqual(client.calls, [])

    async def test_llm_fallback_uses_neighbor_context(self) -> None:
        previous = self.block(0, "Реквизиты сторон")
        candidate = self.block(1, "ООО Альфа")
        following = self.block(2, "Подпись")
        match = self.match(candidate, candidate.text)
        client = PartyLLMClient(PartyRole.BUYER)

        await identify_parties(
            [previous, candidate, following],
            {candidate.block_id: [match]},
            client,
        )

        self.assertEqual(match.party_role, PartyRole.BUYER)
        self.assertEqual(
            client.calls,
            [("\n".join(block.text for block in [previous, candidate, following]), candidate.text)],
        )

    async def test_none_and_unexpected_llm_results_leave_unknown(self) -> None:
        for llm_result in (None, PartyRole.UNKNOWN, "SUPPLIER"):
            with self.subTest(llm_result=llm_result):
                block = self.block(0, "ООО Альфа")
                match = self.match(block, block.text)
                client = PartyLLMClient(llm_result)

                await identify_parties(
                    [block], {block.block_id: [match]}, client
                )

                self.assertEqual(match.party_role, PartyRole.UNKNOWN)
                self.assertEqual(len(client.calls), 1)

    async def test_non_party_and_preclassified_matches_are_untouched(self) -> None:
        block = self.block(0, "Поставщик: ООО Альфа, ИНН 7707083893")
        organization = self.match(
            block,
            "ООО Альфа",
            party_role=PartyRole.BUYER,
        )
        inn = self.match(block, "7707083893", EntityType.INN)
        client = PartyLLMClient(PartyRole.SUPPLIER)

        await identify_parties(
            [block], {block.block_id: [organization, inn]}, client
        )

        self.assertEqual(organization.party_role, PartyRole.BUYER)
        self.assertEqual(inn.party_role, PartyRole.UNKNOWN)
        self.assertEqual(client.calls, [])

    async def test_only_party_role_is_mutated_and_mapping_is_reused(self) -> None:
        block = self.block(0, "Покупатель: АО Бета")
        match = self.match(block, "АО Бета")
        before = {
            field.name: getattr(match, field.name)
            for field in fields(Match)
            if field.name != "party_role"
        }
        matches_by_block = {block.block_id: [match], "extra": []}

        result = await identify_parties(
            [block], matches_by_block, PartyLLMClient()
        )

        after = {
            field.name: getattr(match, field.name)
            for field in fields(Match)
            if field.name != "party_role"
        }
        self.assertIs(result, matches_by_block)
        self.assertEqual(list(result), [block.block_id, "extra"])
        self.assertEqual(after, before)
        self.assertEqual(match.party_role, PartyRole.BUYER)


if __name__ == "__main__":
    unittest.main()
