import asyncio
import inspect
import unittest

from core.models import EntityType, PartyRole
from llm.base import BaseLLMClient
from llm.mock_client import MOCK_CONFIDENCE, MOCK_SOURCE, MockLLMClient


class MockLLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MockLLMClient()

    def find_entities(self, text: str, types: list[EntityType]):
        return asyncio.run(self.client.find_entities(text, types))

    def classify_party(self, context: str, candidate: str):
        return asyncio.run(self.client.classify_party(context, candidate))

    def test_implements_async_contract(self) -> None:
        self.assertIsInstance(self.client, BaseLLMClient)
        self.assertTrue(inspect.iscoroutinefunction(self.client.find_entities))
        self.assertTrue(inspect.iscoroutinefunction(self.client.classify_party))

    def test_finds_supported_requested_entities_with_exact_offsets(self) -> None:
        text = (
            "Поставщик ООО «Ромашка», директор Иванов Иван Иванович. "
            "Адрес: г. Москва, ул. Ленина, д. 10; сумма 125 000,50 руб."
        )
        spans = self.find_entities(
            text,
            [
                EntityType.PERSON_NAME,
                EntityType.ORGANIZATION,
                EntityType.ADDRESS,
                EntityType.AMOUNT,
            ],
        )

        self.assertEqual(
            [span.entity_type for span in spans],
            [
                EntityType.ORGANIZATION,
                EntityType.PERSON_NAME,
                EntityType.ADDRESS,
                EntityType.AMOUNT,
            ],
        )
        for span in spans:
            self.assertEqual(text[span.start : span.end], span.text)
            self.assertEqual(span.source, MOCK_SOURCE)
            self.assertEqual(span.confidence, MOCK_CONFIDENCE)

    def test_respects_requested_types_and_ignores_rule_based_types(self) -> None:
        text = "Иванов Иван Иванович, ИНН 7701234567, ООО «Ромашка»"
        spans = self.find_entities(
            text,
            [EntityType.ORGANIZATION, EntityType.INN],
        )

        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].entity_type, EntityType.ORGANIZATION)
        self.assertEqual(spans[0].text, "ООО «Ромашка»")

    def test_result_is_deterministic_and_duplicate_types_do_not_duplicate_spans(self) -> None:
        text = "Иванов И.И. подписал акт. Иванов И.И. получил копию."
        types = [EntityType.PERSON_NAME, EntityType.PERSON_NAME]

        first = self.find_entities(text, types)
        second = self.find_entities(text, types)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)

    def test_classifies_supplier_and_buyer_by_nearest_role(self) -> None:
        context = "Поставщик: ООО «Ромашка». Покупатель: АО «Вектор»."

        self.assertEqual(
            self.classify_party(context, "ООО «Ромашка»"),
            PartyRole.SUPPLIER,
        )
        self.assertEqual(
            self.classify_party(context, "АО «Вектор»"),
            PartyRole.BUYER,
        )

    def test_classification_returns_none_when_evidence_is_missing_or_ambiguous(self) -> None:
        self.assertIsNone(self.classify_party("Стороны подписали договор", "ООО Ромашка"))
        self.assertIsNone(self.classify_party("Поставщик и покупатель", "Другая компания"))
        self.assertIsNone(self.classify_party("", "ООО Ромашка"))


if __name__ == "__main__":
    unittest.main()
