import asyncio
import inspect
import unittest
from collections.abc import Sequence

from core.models import EntitySpan, EntityType, PartyRole
from llm.base import BaseLLMClient


class ExampleLLMClient(BaseLLMClient):
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
        return None


class BaseLLMClientTests(unittest.TestCase):
    def test_base_class_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            BaseLLMClient()

    def test_contract_methods_are_coroutines(self) -> None:
        self.assertTrue(inspect.iscoroutinefunction(BaseLLMClient.find_entities))
        self.assertTrue(inspect.iscoroutinefunction(BaseLLMClient.classify_party))

    def test_complete_provider_implements_contract(self) -> None:
        client = ExampleLLMClient()
        self.assertEqual(asyncio.run(client.find_entities("", [])), [])
        self.assertIsNone(asyncio.run(client.classify_party("", "")))


if __name__ == "__main__":
    unittest.main()
