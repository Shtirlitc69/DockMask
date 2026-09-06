"""OpenAI-compatible structured-output adapter."""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from llm.http_utils import request_with_retries
from llm.structured import LLMResponseError, StructuredLLMClient
from llm.types import LLMModelInfo, validate_user_base_url


class _Message(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str


class _Choice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    message: _Message


class _Completion(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    choices: list[_Choice]


class OpenAICompatibleClient(StructuredLLMClient):
    """Use the OpenAI Chat Completions wire protocol."""

    source = "openai-compatible"

    def __init__(
        self,
        *,
        model: str,
        http_client: httpx.AsyncClient,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        source: str | None = None,
    ) -> None:
        if not model:
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._model = model
        self._http_client = http_client
        self._base_url = validate_user_base_url(base_url)
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds)
        if source:
            self.source = source

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        }
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            envelope = _Completion.model_validate(response.json())
            return envelope.choices[0].message.content
        except (ValueError, ValidationError, IndexError):
            raise LLMResponseError("Provider returned an invalid chat response") from None

    async def list_models(self) -> list[LLMModelInfo]:
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            data = response.json()["data"]
            models = [
                LLMModelInfo(id=item["id"], display_name=item.get("name", item["id"]))
                for item in data
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        except (TypeError, ValueError, KeyError):
            raise LLMResponseError("Provider returned an invalid model list") from None
        return sorted(models, key=lambda item: item.id.casefold())
