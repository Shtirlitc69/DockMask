"""Тесты обнаружения структурированных и LLM-сущностей."""

import asyncio
import unittest
from collections.abc import Sequence
from itertools import pairwise
from unittest.mock import patch

from core.detectors.entity_detector import LLM_MAX_CONCURRENCY, detect_all
from core.detectors.rule_based import detect_rule_based
from core.models import (
    BlockKind,
    EntitySpan,
    EntityType,
    Location,
    PartyRole,
    TextBlock,
)
from llm.base import BaseLLMClient

ALL_RULE_TYPES = [
    EntityType.INN,
    EntityType.KPP,
    EntityType.OGRN,
    EntityType.PHONE,
    EntityType.EMAIL,
    EntityType.BANK_ACCOUNT,
    EntityType.BIK,
    EntityType.CONTRACT_NUMBER,
]


class RuleBasedDetectorTests(unittest.TestCase):
    def assert_values(
        self,
        text: str,
        requested_types: list[EntityType],
        expected: list[tuple[EntityType, str]],
    ) -> None:
        spans = detect_rule_based(text, requested_types)
        actual = [(span.entity_type, span.text) for span in spans]
        self.assertEqual(actual, expected)
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)
            self.assertEqual(span.source, "rule")
            self.assertEqual(span.confidence, 1.0)

    def test_positive_case_for_every_type(self) -> None:
        cases = (
            ("ИНН: 7707083893", EntityType.INN, "7707083893"),
            ("КПП 773601001", EntityType.KPP, "773601001"),
            ("ОГРН 1027700132195", EntityType.OGRN, "1027700132195"),
            ("телефон: +7 (495) 123-45-67", EntityType.PHONE, "+7 (495) 123-45-67"),
            ("info@example.ru", EntityType.EMAIL, "info@example.ru"),
            (
                "расчётный счёт 40702810900000000001",
                EntityType.BANK_ACCOUNT,
                "40702810900000000001",
            ),
            ("БИК: 044525225", EntityType.BIK, "044525225"),
            (
                "Договор поставки № 15-А/2026",
                EntityType.CONTRACT_NUMBER,
                "15-А/2026",
            ),
        )

        for text, entity_type, value in cases:
            with self.subTest(entity_type=entity_type):
                self.assert_values(text, [entity_type], [(entity_type, value)])

    def test_negative_case_for_every_type(self) -> None:
        cases = (
            ("7707083893", EntityType.INN),
            ("773601001", EntityType.KPP),
            ("ОГРН 1027700132194", EntityType.OGRN),
            ("+7 (495) 123-45-67", EntityType.PHONE),
            ("пишите на info@localhost", EntityType.EMAIL),
            ("40702810900000000001", EntityType.BANK_ACCOUNT),
            ("044525225", EntityType.BIK),
            ("№ 15-А/2026", EntityType.CONTRACT_NUMBER),
        )

        for text, entity_type in cases:
            with self.subTest(entity_type=entity_type):
                self.assert_values(text, [entity_type], [])

    def test_inn_and_kpp_in_combined_requisites(self) -> None:
        text = "ИНН/КПП 7707083893/773601001"
        self.assert_values(
            text,
            [EntityType.INN, EntityType.KPP],
            [
                (EntityType.INN, "7707083893"),
                (EntityType.KPP, "773601001"),
            ],
        )

    def test_inn_control_digits_for_legal_entity_and_person(self) -> None:
        text = "ИНН 7707083893; ИНН 500100732259"
        self.assert_values(
            text,
            [EntityType.INN],
            [
                (EntityType.INN, "7707083893"),
                (EntityType.INN, "500100732259"),
            ],
        )

        self.assert_values(
            "ИНН 7707083894; ИНН 500100732258",
            [EntityType.INN],
            [],
        )

    def test_ogrn_and_ogrnip_control_digits(self) -> None:
        text = "ОГРН 1027700132195; ОГРНИП 304500116000157"
        self.assert_values(
            text,
            [EntityType.OGRN],
            [
                (EntityType.OGRN, "1027700132195"),
                (EntityType.OGRN, "304500116000157"),
            ],
        )

        self.assert_values(
            "ОГРН 1027700132194; ОГРНИП 304500116000156",
            [EntityType.OGRN],
            [],
        )

    def test_account_starting_with_eight_is_not_a_phone(self) -> None:
        account = "81234567890123456789"
        text = f"тел. {account}; р/с {account}"
        self.assert_values(
            text,
            [EntityType.PHONE, EntityType.BANK_ACCOUNT],
            [(EntityType.BANK_ACCOUNT, account)],
        )

    def test_random_ten_digit_number_is_not_inn(self) -> None:
        self.assert_values("Код операции 7707083893", [EntityType.INN], [])

    def test_values_at_text_boundaries_and_two_values_in_one_line(self) -> None:
        text = "first@example.ru, email: second@example.ru; БИК 044525225"
        self.assert_values(
            text,
            [EntityType.EMAIL, EntityType.BIK],
            [
                (EntityType.EMAIL, "first@example.ru"),
                (EntityType.EMAIL, "second@example.ru"),
                (EntityType.BIK, "044525225"),
            ],
        )
        spans = detect_rule_based(text, [EntityType.EMAIL, EntityType.BIK])
        self.assertEqual(spans[0].start, 0)
        self.assertEqual(spans[-1].end, len(text))

    def test_requested_type_filter_empty_input_and_duplicate_types(self) -> None:
        text = "ИНН 7707083893, БИК 044525225, email info@example.ru"
        self.assert_values(text, [], [])
        self.assert_values(
            text,
            [EntityType.INN, EntityType.INN],
            [(EntityType.INN, "7707083893")],
        )

    def test_synthetic_contract_finds_all_marked_entities_without_overlaps(self) -> None:
        text = (
            "Договор поставки № 15-А/2026\n"
            "Реквизиты: ИНН/КПП 7707083893/773601001, ОГРН 1027700132195.\n"
            "р/с 40702810900000000001, БИК 044525225.\n"
            "Телефон: +7 (495) 123-45-67, email: tender@example.ru."
        )
        spans = detect_rule_based(text, ALL_RULE_TYPES)

        self.assertEqual(
            [(span.entity_type, span.text) for span in spans],
            [
                (EntityType.CONTRACT_NUMBER, "15-А/2026"),
                (EntityType.INN, "7707083893"),
                (EntityType.KPP, "773601001"),
                (EntityType.OGRN, "1027700132195"),
                (EntityType.BANK_ACCOUNT, "40702810900000000001"),
                (EntityType.BIK, "044525225"),
                (EntityType.PHONE, "+7 (495) 123-45-67"),
                (EntityType.EMAIL, "tender@example.ru"),
            ],
        )
        for previous, current in pairwise(spans):
            self.assertLessEqual(previous.end, current.start)
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)


class StubLLMClient(BaseLLMClient):
    def __init__(
        self,
        results: dict[str, list[EntitySpan]] | None = None,
        delays: dict[str, float] | None = None,
    ) -> None:
        self.results = results or {}
        self.delays = delays or {}
        self.calls: list[tuple[str, tuple[EntityType, ...]]] = []

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        self.calls.append((text, tuple(types)))
        await asyncio.sleep(self.delays.get(text, 0))
        return list(self.results.get(text, []))

    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        return None


class ConcurrencyLLMClient(StubLLMClient):
    def __init__(self) -> None:
        super().__init__()
        self.active_calls = 0
        self.max_active_calls = 0

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        self.calls.append((text, tuple(types)))
        self.active_calls += 1
        self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            await asyncio.sleep(0.01)
            return []
        finally:
            self.active_calls -= 1


class EntityDetectorTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def block(block_id: str, text: str) -> TextBlock:
        return TextBlock(
            block_id=block_id,
            text=text,
            kind=BlockKind.DOCX_PARAGRAPH,
            location=Location(paragraph_index=int(block_id.removeprefix("p:"))),
        )

    async def test_rule_based_wins_exact_duplicate_from_llm(self) -> None:
        text = "ООО «Альфа»"
        rule_span = EntitySpan(
            EntityType.ORGANIZATION,
            text,
            0,
            len(text),
            source="rule",
            confidence=1.0,
        )
        llm_span = EntitySpan(
            EntityType.ORGANIZATION,
            text,
            0,
            len(text),
            source="llm-test",
            confidence=0.99,
        )
        client = StubLLMClient({text: [llm_span]})

        with patch(
            "core.detectors.entity_detector.detect_rule_based",
            return_value=[rule_span],
        ):
            result = await detect_all(
                [self.block("p:0", text)],
                [EntityType.ORGANIZATION],
                client,
            )

        self.assertEqual(len(result["p:0"]), 1)
        self.assertEqual(result["p:0"][0].source, "rule")

    async def test_llm_overlap_prefers_confidence_then_length(self) -> None:
        confidence_text = "ООО Ромашка"
        confidence_spans = [
            EntitySpan(
                EntityType.ORGANIZATION,
                confidence_text,
                0,
                len(confidence_text),
                source="llm-test",
                confidence=0.6,
            ),
            EntitySpan(
                EntityType.PERSON_NAME,
                "Ромашка",
                4,
                len(confidence_text),
                source="llm-test",
                confidence=0.9,
            ),
        ]
        length_text = "Иван Иванов"
        length_spans = [
            EntitySpan(
                EntityType.PERSON_NAME,
                length_text,
                0,
                len(length_text),
                source="llm-test",
                confidence=0.8,
            ),
            EntitySpan(
                EntityType.ORGANIZATION,
                "Иванов",
                5,
                len(length_text),
                source="llm-test",
                confidence=0.8,
            ),
        ]
        client = StubLLMClient(
            {
                confidence_text: confidence_spans,
                length_text: length_spans,
            }
        )

        result = await detect_all(
            [self.block("p:0", confidence_text), self.block("p:1", length_text)],
            [EntityType.PERSON_NAME, EntityType.ORGANIZATION],
            client,
        )

        self.assertEqual(result["p:0"][0].text, "Ромашка")
        self.assertEqual(result["p:1"][0].text, length_text)

    async def test_non_overlapping_matches_keep_metadata_and_location(self) -> None:
        text = "ООО «Альфа» и Иванов Иван Иванович"
        organization = "ООО «Альфа»"
        person = "Иванов Иван Иванович"
        person_start = text.index(person)
        spans = [
            EntitySpan(
                EntityType.PERSON_NAME,
                person,
                person_start,
                person_start + len(person),
                source="ner-person",
                confidence=0.82,
            ),
            EntitySpan(
                EntityType.ORGANIZATION,
                organization,
                0,
                len(organization),
                source="ner-org",
                confidence=0.91,
            ),
        ]
        block = self.block("p:3", text)

        result = await detect_all(
            [block],
            [EntityType.PERSON_NAME, EntityType.ORGANIZATION],
            StubLLMClient({text: spans}),
        )

        matches = result["p:3"]
        self.assertEqual([match.text for match in matches], [organization, person])
        self.assertEqual(
            [(match.source, match.confidence) for match in matches],
            [("ner-org", 0.91), ("ner-person", 0.82)],
        )
        self.assertTrue(all(match.block_id == "p:3" for match in matches))
        self.assertTrue(all(match.location is block.location for match in matches))
        self.assertLessEqual(matches[0].end, matches[1].start)

    async def test_replacements_are_stable_across_blocks_and_types(self) -> None:
        first_text = "ООО «Альфа» и ООО «Бета»"
        second_text = "Иванов Иван Иванович, ООО «Альфа»"
        alpha = "ООО «Альфа»"
        beta = "ООО «Бета»"
        person = "Иванов Иван Иванович"

        client = StubLLMClient(
            {
                first_text: [
                    EntitySpan(
                        EntityType.ORGANIZATION,
                        alpha,
                        first_text.index(alpha),
                        first_text.index(alpha) + len(alpha),
                    ),
                    EntitySpan(
                        EntityType.ORGANIZATION,
                        beta,
                        first_text.index(beta),
                        first_text.index(beta) + len(beta),
                    ),
                ],
                second_text: [
                    EntitySpan(
                        EntityType.PERSON_NAME,
                        person,
                        0,
                        len(person),
                    ),
                    EntitySpan(
                        EntityType.ORGANIZATION,
                        alpha,
                        second_text.index(alpha),
                        second_text.index(alpha) + len(alpha),
                    ),
                ],
            },
            delays={first_text: 0.02, second_text: 0},
        )

        result = await detect_all(
            [self.block("p:0", first_text), self.block("p:1", second_text)],
            [EntityType.PERSON_NAME, EntityType.ORGANIZATION],
            client,
        )

        self.assertEqual(
            [match.replacement for match in result["p:0"]],
            ["[ORGANIZATION_1]", "[ORGANIZATION_2]"],
        )
        self.assertEqual(
            [match.replacement for match in result["p:1"]],
            ["[PERSON_NAME_1]", "[ORGANIZATION_1]"],
        )

    async def test_llm_is_not_called_for_rule_only_or_empty_blocks(self) -> None:
        client = StubLLMClient()
        rule_result = await detect_all(
            [self.block("p:0", "ИНН 7707083893")],
            [EntityType.INN],
            client,
        )
        empty_result = await detect_all(
            [self.block("p:1", ""), self.block("p:2", "   \t")],
            [EntityType.ORGANIZATION],
            client,
        )

        self.assertEqual(client.calls, [])
        self.assertEqual(rule_result["p:0"][0].entity_type, EntityType.INN)
        self.assertEqual(empty_result, {"p:1": [], "p:2": []})

    async def test_invalid_and_unrequested_llm_spans_are_discarded(self) -> None:
        text = "ООО Альфа"
        valid = EntitySpan(
            EntityType.ORGANIZATION,
            text,
            0,
            len(text),
            source="llm-valid",
            confidence=0.7,
        )
        outside = EntitySpan(
            EntityType.ORGANIZATION,
            "X",
            100,
            101,
            source="llm-outside",
            confidence=0.9,
        )
        mismatch = EntitySpan(
            EntityType.ORGANIZATION,
            "Бета",
            4,
            8,
            source="llm-mismatch",
            confidence=0.9,
        )
        wrong_type = EntitySpan(
            EntityType.INN,
            "ООО",
            0,
            3,
            source="llm-wrong-type",
            confidence=0.9,
        )

        result = await detect_all(
            [self.block("p:0", text)],
            [EntityType.ORGANIZATION],
            StubLLMClient({text: [outside, mismatch, wrong_type, valid]}),
        )

        self.assertEqual(len(result["p:0"]), 1)
        self.assertEqual(result["p:0"][0].source, "llm-valid")

    async def test_llm_parallelism_is_limited(self) -> None:
        blocks = [self.block(f"p:{index}", f"Организация {index}") for index in range(10)]
        client = ConcurrencyLLMClient()

        result = await detect_all(blocks, [EntityType.ORGANIZATION], client)

        self.assertEqual(len(client.calls), len(blocks))
        self.assertEqual(client.max_active_calls, LLM_MAX_CONCURRENCY)
        self.assertTrue(all(result[block.block_id] == [] for block in blocks))


if __name__ == "__main__":
    unittest.main()
