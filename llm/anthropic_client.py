"""Native Anthropic Messages API adapter."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from llm.http_utils import request_with_retries
from llm.structured import LLMResponseError, StructuredLLMClient
from llm.types import LLMModelInfo

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"


class _ContentBlock(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    type: str
    text: str | None = None


class _MessageResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: list[_ContentBlock]


class AnthropicClient(StructuredLLMClient):
    """Use the Anthropic Messages API and structured output format."""

    source = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        http_client: httpx.AsyncClient,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for anthropic")
        if not model:
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key
        self._model = model
        self._http_client = http_client
        self._timeout = httpx.Timeout(timeout_seconds)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Api-Key": self._api_key,
            "Anthropic-Version": ANTHROPIC_VERSION,
        }

    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.post(
                f"{ANTHROPIC_BASE_URL}/messages",
                headers=self._headers(),
                json={
                    "model": self._model,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                    "output_config": {
                        "format": {
                            "type": "json_schema",
                            "schema": response_schema,
                        }
                    },
                },
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            envelope = _MessageResponse.model_validate(response.json())
            return next(
                block.text
                for block in envelope.content
                if block.type == "text" and block.text is not None
            )
        except (ValueError, ValidationError, StopIteration):
            raise LLMResponseError("Anthropic returned an invalid message response") from None

    async def list_models(self) -> list[LLMModelInfo]:
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.get(
                f"{ANTHROPIC_BASE_URL}/models",
                headers=self._headers(),
                params={"limit": 1000},
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            items = response.json()["data"]
            models = [
                LLMModelInfo(
                    id=item["id"],
                    display_name=item.get("display_name", item["id"]),
                    capabilities=tuple(
                        name
                        for name, value in (item.get("capabilities") or {}).items()
                        if value is True
                        or (isinstance(value, dict) and value.get("supported") is True)
                    ),
                )
                for item in items
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        except (TypeError, ValueError, KeyError):
            raise LLMResponseError("Anthropic returned an invalid model list") from None
        return models
