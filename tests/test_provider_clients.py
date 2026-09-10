"""Mock-transport tests for cloud and local provider adapters."""

from __future__ import annotations

import json
import unittest
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import httpx

from core.models import BlockKind, EntityType, Location, PartyRole, TextBlock
from llm.anthropic_client import AnthropicClient
from llm.catalog import list_llm_models, validate_llm_connection
from llm.http_utils import LLMContextLimitError, LLMHTTPError
from llm.ollama_client import OllamaClient
from llm.openai_client import OpenAIClient
from llm.openai_compatible_client import OpenAICompatibleClient
from llm.types import LLMClientConfig, ProviderId, validate_user_base_url
from llm.vllm_client import VLLMClient

Handler = Callable[[httpx.Request], httpx.Response]


def openai_response(request: httpx.Request, content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
        request=request,
    )


class ProviderClientTests(unittest.IsolatedAsyncioTestCase):
    def make_http_client(self, handler: Handler) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_openai_compatible_entities_and_request_contract(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return openai_response(
                request,
                '{"entities":[{"type":"organization","text":"ООО Тест"}]}',
            )

        client = OpenAICompatibleClient(
            model="router-model",
            api_key="router-secret",
            base_url="https://router.example/v1",
            http_client=self.make_http_client(handler),
        )
        spans = await client.find_entities("Компания ООО Тест", [EntityType.ORGANIZATION])
        self.assertEqual([span.text for span in spans], ["ООО Тест"])
        request = requests[0]
        self.assertEqual(request.url.path, "/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer router-secret")
        payload = json.loads(request.content)
        self.assertEqual(payload["model"], "router-model")
        self.assertEqual(payload["response_format"]["type"], "json_schema")

    async def test_all_builtin_structured_providers_batch_many_blocks_once(self) -> None:
        blocks = [
            TextBlock(
                block_id=f"p:{index}",
                text=f"Организация {index}",
                kind=BlockKind.DOCX_PARAGRAPH,
                location=Location(paragraph_index=index),
            )
            for index in range(101)
        ]
        content = (
            '{"entities":[{"block_id":100,"type":"organization",'
            '"text":"Организация 100","party_role":"buyer"}]}'
        )
        cases = (
            (
                "openai",
                lambda http: OpenAIClient(
                    api_key="key",
                    model="model",
                    http_client=http,
                ),
                120_000,
            ),
            (
                "anthropic",
                lambda http: AnthropicClient(
                    api_key="key",
                    model="model",
                    http_client=http,
                ),
                120_000,
            ),
            (
                "openai-compatible",
                lambda http: OpenAICompatibleClient(
                    model="model",
                    base_url="https://router.example/v1",
                    http_client=http,
                ),
                24_000,
            ),
            (
                "ollama",
                lambda http: OllamaClient(model="model", http_client=http),
                24_000,
            ),
            (
                "vllm",
                lambda http: VLLMClient(model="model", http_client=http),
                24_000,
            ),
        )
        for name, factory, expected_limit in cases:
            with self.subTest(provider=name):
                requests: list[httpx.Request] = []

                def handler(
                    request: httpx.Request,
                    captured: list[httpx.Request] = requests,
                ) -> httpx.Response:
                    captured.append(request)
                    if request.url.path.endswith("/messages"):
                        return httpx.Response(
                            200,
                            json={"content": [{"type": "text", "text": content}]},
                            request=request,
                        )
                    if request.url.path.endswith("/api/chat"):
                        return httpx.Response(
                            200,
                            json={"message": {"content": content}},
                            request=request,
                        )
                    return openai_response(request, content)

                client = factory(self.make_http_client(handler))
                result = await client.find_entities_in_blocks(
                    blocks,
                    [EntityType.ORGANIZATION],
                )

                self.assertEqual(len(requests), 1)
                self.assertEqual(client.batch_max_chars, expected_limit)
                self.assertEqual(client.batch_max_concurrency, 1)
                self.assertEqual(result["p:100"][0].party_role, PartyRole.BUYER)

    async def test_openai_uses_official_endpoint_and_lists_models(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "api.openai.com")
            return httpx.Response(
                200,
                json={"data": [{"id": "model-b"}, {"id": "model-a"}]},
                request=request,
            )

        client = OpenAIClient(
            api_key="openai-secret",
            model="model-a",
            http_client=self.make_http_client(handler),
        )
        models = await client.list_models()
        self.assertEqual([model.id for model in models], ["model-a", "model-b"])

    async def test_anthropic_role_and_model_list(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/models"):
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "claude-test",
                                "display_name": "Claude Test",
                                "capabilities": {
                                    "structured_outputs": {"supported": True}
                                },
                            }
                        ]
                    },
                    request=request,
                )
            return httpx.Response(
                200,
                json={"content": [{"type": "text", "text": '{"role":"buyer"}'}]},
                request=request,
            )

        client = AnthropicClient(
            api_key="anthropic-secret",
            model="claude-test",
            http_client=self.make_http_client(handler),
        )
        role = await client.classify_party("Покупатель Компания", "Компания")
        models = await client.list_models()
        self.assertEqual(role, PartyRole.BUYER)
        self.assertEqual(models[0].display_name, "Claude Test")
        self.assertIn("structured_outputs", models[0].capabilities)
        self.assertTrue(all(req.headers["X-Api-Key"] == "anthropic-secret" for req in requests))
        self.assertTrue(all("Anthropic-Version" in req.headers for req in requests))

    async def test_ollama_native_contract_and_models(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/tags":
                return httpx.Response(
                    200,
                    json={"models": [{"name": "qwen:latest", "model": "qwen:latest"}]},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"message": {"content": '{"role":"supplier"}'}},
                request=request,
            )

        client = OllamaClient(model="qwen:latest", http_client=self.make_http_client(handler))
        role = await client.classify_party("Поставщик Компания", "Компания")
        models = await client.list_models()
        self.assertEqual(role, PartyRole.SUPPLIER)
        self.assertEqual(models[0].id, "qwen:latest")
        payload = json.loads(requests[0].content)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertIsInstance(payload["format"], dict)

    async def test_vllm_is_distinct_openai_compatible_adapter(self) -> None:
        client = VLLMClient(
            model="local",
            http_client=self.make_http_client(
                lambda request: openai_response(request, '{"role":"unknown"}')
            ),
        )
        self.assertIsInstance(client, OpenAICompatibleClient)
        self.assertEqual(client.source, "vllm")
        self.assertIsNone(await client.classify_party("Компания", "Компания"))

    async def test_retry_limit_and_safe_http_error(self) -> None:
        calls = 0
        secret = "secret-not-in-error"

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, text=secret, request=request)

        client = OpenAICompatibleClient(
            model="model",
            api_key=secret,
            base_url="https://router.example/v1",
            http_client=self.make_http_client(handler),
        )
        with (
            patch("llm.http_utils.asyncio.sleep", return_value=None),
            self.assertRaises(LLMHTTPError) as raised,
        ):
            await client.classify_party("Поставщик Тест", "Тест")
        self.assertEqual(calls, 3)
        self.assertNotIn(secret, str(raised.exception))

    async def test_retry_after_is_honored_with_three_total_attempts(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls < 3:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "7"},
                    request=request,
                )
            return openai_response(request, '{"role":"unknown"}')

        client = OpenAICompatibleClient(
            model="model",
            base_url="https://router.example/v1",
            http_client=self.make_http_client(handler),
        )
        sleep = AsyncMock()
        with (
            patch("llm.http_utils.asyncio.sleep", new=sleep),
            patch("llm.http_utils.random.uniform", return_value=0.0),
        ):
            await client.classify_party("Компания", "Компания")

        self.assertEqual(calls, 3)
        self.assertEqual([item.args[0] for item in sleep.await_args_list], [7.0, 7.0])

    async def test_context_limit_is_safe_and_is_not_retried(self) -> None:
        calls = 0
        secret = "private-prompt-value"

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "context_length_exceeded",
                        "message": secret,
                    }
                },
                request=request,
            )

        client = OpenAICompatibleClient(
            model="model",
            base_url="https://router.example/v1",
            http_client=self.make_http_client(handler),
        )
        with self.assertRaises(LLMContextLimitError) as raised:
            await client.classify_party("Компания", "Компания")

        self.assertEqual(calls, 1)
        self.assertNotIn(secret, str(raised.exception))

    async def test_catalog_lists_models_and_validates(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "model"}]}, request=request)
            return openai_response(request, '{"role":"supplier"}')

        config = LLMClientConfig(
            ProviderId.OPENAI_COMPATIBLE,
            "model",
            base_url="https://router.example/v1",
        )
        http_client = self.make_http_client(handler)
        self.assertEqual((await list_llm_models(config, http_client))[0].id, "model")
        result = await validate_llm_connection(config, http_client)
        self.assertTrue(result.ok)
        self.assertEqual(result.code, "ok")

    def test_url_policy(self) -> None:
        accepted = (
            "http://localhost:11434",
            "http://127.0.0.1:8000/v1",
            "http://[::1]:8000/v1",
            "https://router.example/v1/",
        )
        for url in accepted:
            with self.subTest(url=url):
                self.assertTrue(validate_user_base_url(url))
        rejected = (
            "http://192.168.1.2:8000/v1",
            "ftp://router.example",
            "https://user:pass@router.example/v1",
            "https://router.example/v1?token=secret",
            "https://router.example/v1#fragment",
        )
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_user_base_url(url)


if __name__ == "__main__":
    unittest.main()
