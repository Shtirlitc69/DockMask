"""Native Ollama structured-output adapter."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from llm.http_utils import request_with_retries
from llm.structured import LLMResponseError, StructuredLLMClient
from llm.types import LLMModelInfo, validate_user_base_url

OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434"


class _OllamaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str


class _OllamaResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    message: _OllamaMessage


class OllamaClient(StructuredLLMClient):
    """Use Ollama's native non-streaming chat and model APIs."""

    source = "ollama"

    def __init__(
        self,
        *,
        model: str,
        http_client: httpx.AsyncClient,
        base_url: str = OLLAMA_DEFAULT_BASE_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not model:
            raise ValueError("model must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._model = model
        self._http_client = http_client
        self._base_url = validate_user_base_url(base_url)
        self._timeout = httpx.Timeout(timeout_seconds)

    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
        *,
        system_prompt: str | None = None,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": messages,
                    "format": response_schema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            return _OllamaResponse.model_validate(response.json()).message.content
        except (ValueError, ValidationError):
            raise LLMResponseError("Ollama returned an invalid chat response") from None

    async def list_models(self) -> list[LLMModelInfo]:
        response = await request_with_retries(
            self.source,
            lambda: self._http_client.get(
                f"{self._base_url}/api/tags",
                timeout=self._timeout,
                follow_redirects=False,
            ),
        )
        try:
            items = response.json()["models"]
            models = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                model_id = item.get("model") or item.get("name")
                if not isinstance(model_id, str):
                    continue
                display_name = item.get("name") or model_id
                models.append(
                    LLMModelInfo(
                        id=model_id,
                        display_name=display_name,
                        capabilities=("structured_output",),
                    )
                )
        except (TypeError, ValueError, KeyError):
            raise LLMResponseError("Ollama returned an invalid model list") from None
        return sorted(models, key=lambda item: item.id.casefold())
