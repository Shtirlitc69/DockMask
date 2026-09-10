"""Official OpenAI adapter built on the OpenAI-compatible protocol."""

from __future__ import annotations

import httpx

from llm.openai_compatible_client import OpenAICompatibleClient

OPENAI_BASE_URL = "https://api.openai.com/v1"


class OpenAIClient(OpenAICompatibleClient):
    """OpenAI client with a fixed official API endpoint."""

    source = "openai"
    provider_name = "openai"
    batch_max_chars = 120_000

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for openai")
        super().__init__(
            api_key=api_key,
            model=model,
            http_client=http_client,
            base_url=OPENAI_BASE_URL,
            timeout_seconds=timeout_seconds,
            source=self.source,
        )
