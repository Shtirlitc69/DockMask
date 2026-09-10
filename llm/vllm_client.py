"""vLLM adapter using its OpenAI-compatible server."""

from __future__ import annotations

import httpx

from llm.openai_compatible_client import OpenAICompatibleClient

VLLM_DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"


class VLLMClient(OpenAICompatibleClient):
    """Thin provider-specific wrapper around the common wire protocol."""

    source = "vllm"
    provider_name = "vllm"

    def __init__(
        self,
        *,
        model: str,
        http_client: httpx.AsyncClient,
        base_url: str = VLLM_DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            http_client=http_client,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            source=self.source,
        )
