"""Single construction point for provider-specific LLM clients."""

from __future__ import annotations

import httpx

from llm.anthropic_client import AnthropicClient
from llm.base import BaseLLMClient
from llm.gigachat_client import GigaChatClient
from llm.mock_client import MockLLMClient
from llm.ollama_client import OLLAMA_DEFAULT_BASE_URL, OllamaClient
from llm.openai_client import OpenAIClient
from llm.openai_compatible_client import OpenAICompatibleClient
from llm.types import GigaChatScope, LLMClientConfig, LLMProviderSpec, ProviderId
from llm.vllm_client import VLLM_DEFAULT_BASE_URL, VLLMClient

GIGACHAT_BASE_URL = "https://api.giga.chat"
GIGACHAT_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGACHAT_DEFAULT_SCOPE = GigaChatScope.PERS.value

PROVIDER_SPECS: tuple[LLMProviderSpec, ...] = (
    LLMProviderSpec(
        ProviderId.MOCK,
        "Локальный режим (без LLM)",
        requires_api_key=False,
        requires_base_url=False,
        supports_model_listing=False,
        development_only=False,
    ),
    LLMProviderSpec(ProviderId.GIGACHAT, "GigaChat", True, False),
    LLMProviderSpec(ProviderId.OPENAI, "OpenAI", True, False),
    LLMProviderSpec(ProviderId.ANTHROPIC, "Anthropic", True, False),
    LLMProviderSpec(ProviderId.OPENAI_COMPATIBLE, "OpenAI-compatible", False, True),
    LLMProviderSpec(
        ProviderId.OLLAMA,
        "Ollama",
        False,
        False,
        default_base_url=OLLAMA_DEFAULT_BASE_URL,
    ),
    LLMProviderSpec(
        ProviderId.VLLM,
        "vLLM",
        False,
        False,
        default_base_url=VLLM_DEFAULT_BASE_URL,
    ),
)


def get_provider_specs() -> tuple[LLMProviderSpec, ...]:
    """Return immutable metadata for every registered provider."""

    return PROVIDER_SPECS


def get_llm_client(
    config: LLMClientConfig,
    http_client: httpx.AsyncClient | None,
) -> BaseLLMClient:
    """Create an adapter from already-resolved values without reading state."""

    try:
        provider = ProviderId(config.provider)
    except ValueError:
        supported = ", ".join(item.value for item in ProviderId)
        raise ValueError(f"unknown LLM provider; supported providers: {supported}") from None

    if not config.model:
        raise ValueError("model must not be empty")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if provider is ProviderId.MOCK:
        return MockLLMClient()
    if http_client is None:
        raise ValueError("http_client is required for network LLM providers")

    if provider is ProviderId.GIGACHAT:
        if not config.api_key:
            raise ValueError("api_key is required for gigachat")
        return GigaChatClient(
            auth_key=config.api_key,
            scope=config.scope or GIGACHAT_DEFAULT_SCOPE,
            model=config.model,
            http_client=http_client,
            oauth_url=config.oauth_url or GIGACHAT_OAUTH_URL,
            base_url=config.base_url or GIGACHAT_BASE_URL,
            timeout_seconds=config.timeout_seconds,
        )
    if provider is ProviderId.OPENAI:
        if not config.api_key:
            raise ValueError("api_key is required for openai")
        return OpenAIClient(
            api_key=config.api_key,
            model=config.model,
            http_client=http_client,
            timeout_seconds=config.timeout_seconds,
        )
    if provider is ProviderId.ANTHROPIC:
        if not config.api_key:
            raise ValueError("api_key is required for anthropic")
        return AnthropicClient(
            api_key=config.api_key,
            model=config.model,
            http_client=http_client,
            timeout_seconds=config.timeout_seconds,
        )
    if provider is ProviderId.OPENAI_COMPATIBLE:
        if not config.base_url:
            raise ValueError("base_url is required for openai_compatible")
        return OpenAICompatibleClient(
            api_key=config.api_key,
            model=config.model,
            http_client=http_client,
            base_url=config.base_url,
            timeout_seconds=config.timeout_seconds,
        )
    if provider is ProviderId.OLLAMA:
        return OllamaClient(
            model=config.model,
            http_client=http_client,
            base_url=config.base_url or OLLAMA_DEFAULT_BASE_URL,
            timeout_seconds=config.timeout_seconds,
        )
    if provider is ProviderId.VLLM:
        return VLLMClient(
            api_key=config.api_key,
            model=config.model,
            http_client=http_client,
            base_url=config.base_url or VLLM_DEFAULT_BASE_URL,
            timeout_seconds=config.timeout_seconds,
        )
    raise AssertionError("all ProviderId values must be handled")
