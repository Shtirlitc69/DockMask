"""Offline regressions for GigaChat generation safeguards."""

import asyncio
import json
import unittest

import httpx

from core.detectors.entity_detector import detect_all
from core.models import BlockKind, EntityType, Location, TextBlock
from llm.http_utils import LLMContextLimitError, is_context_limit_response
from llm.request_budget import LLMRequestBudgetError, request_budget
from llm.structured import LLMFilteredResponseError, LLMTruncatedResponseError
from tests import test_gigachat_client as helpers

chat_response = helpers.chat_response
entities_content = helpers.entities_content
token_response = helpers.token_response


class RequestSafetyTests(unittest.IsolatedAsyncioTestCase):
    make_client = helpers.GigaChatClientTests.make_client

    async def test_finish_reason_prevents_accepting_partial_valid_json(self):
        for reason, error in (
            ("length", LLMTruncatedResponseError),
            ("blacklist", LLMFilteredResponseError),
            ("content_filter", LLMFilteredResponseError),
        ):
            with self.subTest(reason=reason):
                def handler(request, finish_reason=reason):
                    if request.url.path == "/api/v2/oauth":
                        return token_response(request)
                    return httpx.Response(200, json={"choices": [{
                        "message": {"content": entities_content()}, "finish_reason": finish_reason,
                    }]})

                client = self.make_client(handler)
                with self.assertRaises(error):
                    await client.find_entities("text", [EntityType.ORGANIZATION])

    async def test_budget_counts_transport_retries_and_resets(self):
        calls = 0

        def handler(request):
            nonlocal calls
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            calls += 1
            return httpx.Response(401)

        client = self.make_client(handler)
        with request_budget(1) as budget:
            with self.assertRaises(LLMRequestBudgetError):
                await client.find_entities("text", [EntityType.ORGANIZATION])
            self.assertEqual(budget.used, 1)
        self.assertEqual(calls, 1)
        with request_budget(1) as budget:
            self.assertEqual(budget.used, 0)

    async def test_separate_clients_share_gate_and_cancelled_waiter_releases(self):
        active = 0
        peak = 0
        entered = asyncio.Event()
        release = asyncio.Event()

        async def handler(request):
            nonlocal active, peak
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            active += 1
            peak = max(active, peak)
            entered.set()
            await release.wait()
            active -= 1
            return chat_response(request, entities_content())

        first, second = self.make_client(handler), self.make_client(handler)
        task = asyncio.create_task(first.find_entities("a", [EntityType.ORGANIZATION]))
        await entered.wait()
        waiter = asyncio.create_task(second.find_entities("b", [EntityType.ORGANIZATION]))
        await asyncio.sleep(0)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        release.set()
        await task
        await second.find_entities("c", [EntityType.ORGANIZATION])
        self.assertEqual(peak, 1)

    async def test_full_request_budget_rejects_before_network(self):
        def handler(request):
            self.fail("over-budget prompt must not reach transport")

        client = self.make_client(handler)
        with self.assertRaises(LLMContextLimitError):
            await client.find_entities("Я" * 40_000, [EntityType.ORGANIZATION])

    async def test_corrupt_schema_response_retries_prompt_schema_with_validation(self):
        bodies = []

        def handler(request):
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            body = json.loads(request.content)
            bodies.append(body)
            if body["response_format"]["type"] == "json_schema":
                return chat_response(request, '{"entities": [garbage]}')
            return chat_response(request, entities_content({
                "type": "person_name", "text": "Alice Example",
            }))

        client = self.make_client(handler)
        client._min_interval = 0
        with request_budget(3) as budget:
            first = await client.find_entities("Alice Example", [EntityType.PERSON_NAME])
            second = await client.find_entities("Alice Example", [EntityType.PERSON_NAME])
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(budget.used, 3)
        self.assertEqual([b["response_format"]["type"] for b in bodies],
                         ["json_schema", "text", "text"])
        self.assertIn('"required"', bodies[1]["messages"][0]["content"])

    async def test_large_document_is_bounded_and_truncation_splits(self):
        calls = 0

        def handler(request):
            nonlocal calls
            if request.url.path == "/api/v2/oauth":
                return token_response(request)
            calls += 1
            if calls == 1:
                return httpx.Response(200, json={"choices": [{
                    "message": {"content": '{"entities":['}, "finish_reason": "length",
                }]})
            return chat_response(request, entities_content())

        client = self.make_client(handler)
        client._min_interval = 0
        blocks = [TextBlock(
            block_id=f"p:{i}", text="Обычный текст " * 9,
            kind=BlockKind.DOCX_PARAGRAPH, location=Location(paragraph_index=i),
        ) for i in range(531)]
        with request_budget() as budget:
            result = await detect_all(blocks, [EntityType.ORGANIZATION], client)
        self.assertEqual(len(result), 531)
        self.assertGreater(calls, 1)
        self.assertLess(calls, 20)
        self.assertEqual(calls, budget.used)

    def test_422_is_context_error_only_with_matching_reason(self):
        self.assertTrue(is_context_limit_response(httpx.Response(
            422, json={"error": {"code": "context_length_exceeded"}}
        )))
        self.assertFalse(is_context_limit_response(httpx.Response(
            422, json={"error": {"message": "invalid schema"}}
        )))
