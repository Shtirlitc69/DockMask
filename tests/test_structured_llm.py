"""Shared structured-output contract tests."""

from __future__ import annotations

import unittest

from core.models import EntityType
from llm.structured import LLMResponseError, StructuredLLMClient


class StubStructuredClient(StructuredLLMClient):
    source = "stub-provider"

    def __init__(self, content: str) -> None:
        self.content = content

    async def _complete(self, prompt, response_schema, *, system_prompt=None):
        del prompt, response_schema, system_prompt
        return self.content


class StructuredLLMTests(unittest.IsolatedAsyncioTestCase):
    async def test_fenced_json_repeated_values_and_duplicates(self) -> None:
        client = StubStructuredClient(
            '```json\n{"entities":['
            '{"type":"person_name","text":"Иванов И.И."},'
            '{"type":"person_name","text":"Иванов И.И."}]}\n```'
        )
        text = "Иванов И.И. встретил Иванов И.И."
        spans = await client.find_entities(text, [EntityType.PERSON_NAME])
        self.assertEqual([(span.start, span.end) for span in spans], [(0, 11), (21, 32)])
        self.assertTrue(all(span.source == "stub-provider" for span in spans))

    async def test_unknown_unrequested_and_absent_values_are_ignored(self) -> None:
        client = StubStructuredClient(
            '{"entities":['
            '{"type":"other","text":"СЕКРЕТ-1"},'
            '{"type":"email","text":"СЕКРЕТ-2"},'
            '{"type":"person_name","text":"СЕКРЕТ-3"}]}'
        )
        with self.assertLogs("llm.structured", level="WARNING") as logs:
            spans = await client.find_entities("Без совпадений", [EntityType.PERSON_NAME])
        self.assertEqual(spans, [])
        joined = " ".join(logs.output)
        for value in ("СЕКРЕТ-1", "СЕКРЕТ-2", "СЕКРЕТ-3"):
            self.assertNotIn(value, joined)

    async def test_invalid_json_raises_safe_error(self) -> None:
        rejected = "PRIVATE-MODEL-OUTPUT"
        client = StubStructuredClient(rejected)
        with self.assertRaises(LLMResponseError) as raised:
            await client.classify_party("Поставщик Тест", "Тест")
        self.assertNotIn(rejected, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
