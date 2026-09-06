"""Tests for provider selection without application-layer dependencies."""

from __future__ import annotations

import unittest

import httpx

from llm.anthropic_client import AnthropicClient
from llm.base import BaseLLMClient
from llm.factory import get_llm_client, get_provider_specs
from llm.gigachat_client import GigaChatClient
from llm.mock_client import MockLLMClient
from llm.ollama_client import OllamaClient
from llm.openai_client import OpenAIClient
from llm.openai_compatible_client import OpenAICompatibleClient
from llm.types import LLMClientConfig, ProviderId
from llm.vllm_client import VLLMClient


class LLMFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.http_client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200))
        )

    def tearDown(self) -> None:
        import asyncio

        asyncio.run(self.http_client.aclose())

    def test_selects_every_supported_provider(self) -> None:
        cases = [
            (LLMClientConfig(ProviderId.MOCK, "mock"), MockLLMClient, None),
            (
                LLMClientConfig(ProviderId.GIGACHAT, "GigaChat-2", api_key="key"),
                GigaChatClient,
                self.http_client,
            ),
            (
                LLMClientConfig(ProviderId.OPENAI, "gpt-test", api_key="key"),
                OpenAIClient,
                self.http_client,
            ),
            (
                LLMClientConfig(ProviderId.ANTHROPIC, "claude-test", api_key="key"),
                AnthropicClient,
                self.http_client,
            ),
            (
                LLMClientConfig(
                    ProviderId.OPENAI_COMPATIBLE,
                    "router-model",
                    base_url="https://router.example/v1",
                ),
                OpenAICompatibleClient,
                self.http_client,
            ),
            (
                LLMClientConfig(ProviderId.OLLAMA, "qwen-test"),
                OllamaClient,
                self.http_client,
            ),
            (
                LLMClientConfig(ProviderId.VLLM, "local-test"),
                VLLMClient,
                self.http_client,
            ),
        ]
        for config, expected_type, http_client in cases:
            with self.subTest(provider=config.provider):
                client = get_llm_client(config, http_client)
                self.assertIsInstance(client, expected_type)
                self.assertIsInstance(client, BaseLLMClient)

    def test_network_provider_requires_injected_http_client(self) -> None:
        config = LLMClientConfig(ProviderId.OPENAI, "model", api_key="secret")
        with self.assertRaisesRegex(ValueError, "http_client is required"):
            get_llm_client(config, None)

    def test_required_values_are_validated_without_secret_value(self) -> None:
        secret = "never-include-this-value"
        config = LLMClientConfig(ProviderId.ANTHROPIC, "model", api_key=None)
        with self.assertRaises(ValueError) as raised:
            get_llm_client(config, self.http_client)
        self.assertNotIn(secret, str(raised.exception))

    def test_unknown_provider_lists_supported_values(self) -> None:
        config = LLMClientConfig("other", "model")
        with self.assertRaisesRegex(ValueError, "supported providers:.*gigachat"):
            get_llm_client(config, self.http_client)

    def test_factory_does_not_import_application_layers(self) -> None:
        import inspect

        import llm.factory

        source = inspect.getsource(llm.factory)
        for forbidden in ("os.environ", "core.config", "FastAPI", "keyring"):
            self.assertNotIn(forbidden, source)

    def test_provider_specs_cover_every_provider(self) -> None:
        specs = get_provider_specs()
        self.assertEqual({spec.id for spec in specs}, set(ProviderId))
        mock = next(spec for spec in specs if spec.id is ProviderId.MOCK)
        custom = next(
            spec for spec in specs if spec.id is ProviderId.OPENAI_COMPATIBLE
        )
        self.assertTrue(mock.development_only)
        self.assertTrue(custom.requires_base_url)
        self.assertFalse(custom.requires_api_key)


if __name__ == "__main__":
    unittest.main()
