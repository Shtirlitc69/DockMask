"""Asynchronous GigaChat adapter with OAuth token caching."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Self
from uuid import uuid4
from weakref import WeakKeyDictionary

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from llm.http_utils import (
    LLMContextLimitError,
    LLMHTTPError,
    LLMProviderError,
    _retry_after_seconds,
    is_context_limit_response,
    retry_delay,
)
from llm.request_budget import consume_request
from llm.structured import (
    LLMFilteredResponseError,
    LLMResponseError,
    LLMTruncatedResponseError,
    StructuredLLMClient,
)
from llm.types import LLMModelInfo

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"
MAX_ATTEMPTS = 3
TOKEN_SAFETY_RATIO = 0.1
USER_AGENT = "DockMask/0.1"
LOGGER = logging.getLogger(__name__)


class _GenerationGate:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.ready_at = 0.0


# Application-wide within an event loop, including separately constructed probes.
_GATES: WeakKeyDictionary = WeakKeyDictionary()


def _generation_gate() -> _GenerationGate:
    loop = asyncio.get_running_loop()
    if loop not in _GATES:
        _GATES[loop] = _GenerationGate()
    return _GATES[loop]


class GigaChatError(LLMProviderError):
    """Base error raised by the GigaChat adapter."""


class GigaChatHTTPError(GigaChatError, LLMHTTPError):
    """A safe HTTP error which never includes response bodies or secrets."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        LLMProviderError.__init__(
            self,
            f"GigaChat HTTP request failed with status {status_code}",
        )


class _TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    access_token: str
    expires_at: int | float


class _ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    content: str


class _ChatChoice(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    message: _ChatMessage
    finish_reason: str | None = None


class _ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    choices: list[_ChatChoice]


class GigaChatClient(StructuredLLMClient):
    """Call GigaChat through an injected or internally owned HTTP client."""

    batch_max_chars = 12_000
    batch_max_concurrency = 1
    provides_inline_roles = True
    provider_name = "gigachat"
    source = "gigachat"
    confidence = 0.8

    def __init__(
        self,
        auth_key: str,
        scope: str,
        model: str,
        http_client: httpx.AsyncClient | None,
        oauth_url: str,
        base_url: str,
        timeout_seconds: float = 30.0,
        *,
        context_tokens: int | None = None,
        output_tokens: int = 4096,
        min_interval_seconds: float = 0.25,
    ) -> None:
        if not auth_key:
            raise ValueError("auth_key must not be empty")
        if not scope or not model or not oauth_url or not base_url:
            raise ValueError("GigaChat configuration values must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        # Conservative fallback for unknown/legacy models; caller may override.
        self._context_tokens = context_tokens or (
            128_000 if model in {"GigaChat-2", "GigaChat-2-Pro", "GigaChat-2-Max"}
            else 32_768
        )
        if output_tokens <= 0 or self._context_tokens <= output_tokens + 2048:
            raise ValueError("invalid context/output token budget")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must be nonnegative")
        self._output_tokens = output_tokens
        self.batch_input_token_limit = self._context_tokens - self._output_tokens - 2048
        self._min_interval = min_interval_seconds

        self._auth_key = auth_key
        self._scope = scope
        self._model = model
        self._oauth_url = oauth_url.rstrip("/")
        self._base_url = base_url.rstrip("/")
        self._chat_url = f"{self._base_url}{CHAT_COMPLETIONS_PATH}"
        self._timeout = httpx.Timeout(timeout_seconds)
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(verify=True)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close the HTTP client when this adapter created it."""

        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def list_models(self) -> list[LLMModelInfo]:
        """Return chat models available to the configured GigaChat account."""

        token = await self._get_token()
        attempt = 0
        refreshed_after_401 = False
        while True:
            try:
                response = await self._http_client.get(
                    f"{self._base_url}{MODELS_PATH}",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "User-Agent": USER_AGENT,
                    },
                    timeout=self._timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                attempt += 1
                if attempt >= MAX_ATTEMPTS:
                    raise GigaChatError(
                        "GigaChat model list failed after retryable network errors"
                    ) from exc
                await retry_delay(attempt)
                continue
            if response.status_code == 401 and not refreshed_after_401:
                refreshed_after_401 = True
                token = await self._refresh_rejected_token(token)
                continue
            if self._is_retryable_status(response.status_code):
                attempt += 1
                if attempt < MAX_ATTEMPTS:
                    await retry_delay(attempt, response)
                    continue
            break
        if not 200 <= response.status_code < 300:
            raise GigaChatHTTPError(response.status_code)
        try:
            data = response.json()["data"]
            models = [
                LLMModelInfo(
                    id=item["id"],
                    display_name=item["id"],
                    capabilities=("structured_output",),
                )
                for item in data
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and item.get("type", "chat") == "chat"
            ]
        except (TypeError, ValueError, KeyError):
            raise LLMResponseError("GigaChat returned an invalid model list") from None
        return sorted(models, key=lambda item: item.id.casefold())

    async def _complete(
        self,
        prompt: str,
        response_schema: dict[str, object],
        *,
        system_prompt: str | None = None,
    ) -> str:
        gate = _generation_gate()
        async with gate.lock:
            delay = gate.ready_at - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            try:
                return await self._complete_serialized(
                    prompt, response_schema, system_prompt=system_prompt
                )
            finally:
                gate.ready_at = max(gate.ready_at, time.monotonic() + self._min_interval)

    async def _complete_serialized(
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
        payload = {
            "model": self._model,
            "max_tokens": self._output_tokens,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "schema": response_schema,
                "strict": True,
            },
        }
        # UTF-8 bytes deliberately overestimate tokens; includes schema and framing.
        estimated_tokens = len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) + 256
        if estimated_tokens + self._output_tokens > self._context_tokens:
            raise LLMContextLimitError("GigaChat full request exceeds local context budget")
        batch_id = uuid4().hex
        stage = "party" if "role" in response_schema.get("properties", {}) else "entities"
        transient_attempt = 0
        refreshed_after_401 = False
        token = await self._get_token()

        while True:
            try:
                consume_request()
                started = time.monotonic()
                response = await self._http_client.post(
                    self._chat_url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "User-Agent": USER_AGENT,
                    },
                    json=payload,
                    timeout=self._timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                transient_attempt += 1
                if transient_attempt >= MAX_ATTEMPTS:
                    raise GigaChatError(
                        "GigaChat request failed after retryable network errors"
                    ) from exc
                await retry_delay(transient_attempt)
                continue

            LOGGER.info(
                "gigachat_generation stage=%s model=%s batch=%s status=%d duration_ms=%d",
                stage, self._model, batch_id, response.status_code,
                int((time.monotonic() - started) * 1000),
            )
            if response.status_code == 429:
                cooldown = _retry_after_seconds(response)
                gate = _generation_gate()
                gate.ready_at = max(
                    gate.ready_at, time.monotonic() + max(1.0, cooldown or 0.0)
                )
            if response.status_code == 401 and not refreshed_after_401:
                refreshed_after_401 = True
                token = await self._refresh_rejected_token(token)
                continue
            if is_context_limit_response(response):
                raise LLMContextLimitError(
                    "GigaChat request exceeded the model context limit"
                )
            if self._is_retryable_status(response.status_code):
                transient_attempt += 1
                if transient_attempt < MAX_ATTEMPTS:
                    await retry_delay(transient_attempt, response)
                    await asyncio.sleep(max(0.0, _generation_gate().ready_at - time.monotonic()))
                    continue
            if not 200 <= response.status_code < 300:
                raise GigaChatHTTPError(response.status_code)

            try:
                raw = response.json()
                envelope = _ChatResponse.model_validate(raw)
                choice = envelope.choices[0]
            except (ValueError, ValidationError, IndexError):
                LOGGER.warning("gigachat_validation batch=%s category=invalid_envelope", batch_id)
                raise LLMResponseError(
                    "GigaChat returned an invalid chat response"
                ) from None
            reason = choice.finish_reason
            safe_reason = reason if reason in {None, "stop", "length", "blacklist", "content_filter"} else "other"
            usage = raw.get("usage", {})
            safe_usage = {
                key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage, dict) and type(value := usage.get(key)) is int
            }
            LOGGER.info(
                "gigachat_completion batch=%s finish_reason=%s usage=%s",
                batch_id, safe_reason, safe_usage,
            )
            if reason == "length":
                raise LLMTruncatedResponseError("GigaChat output token limit reached")
            if reason in {"blacklist", "content_filter"}:
                raise LLMFilteredResponseError("GigaChat response filtered")
            if reason not in {None, "stop"}:
                raise LLMResponseError("GigaChat returned an unsupported finish reason")
            return choice.message.content

    async def _get_token(self) -> str:
        if self._token_is_valid():
            assert self._token is not None
            return self._token

        async with self._token_lock:
            if self._token_is_valid():
                assert self._token is not None
                return self._token
            return await self._request_token()

    async def _refresh_rejected_token(self, rejected_token: str) -> str:
        async with self._token_lock:
            if self._token != rejected_token and self._token_is_valid():
                assert self._token is not None
                return self._token
            self._token = None
            self._token_expires_at = 0.0
            return await self._request_token()

    async def _request_token(self) -> str:
        attempt = 0
        while True:
            try:
                response = await self._http_client.post(
                    self._oauth_url,
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Basic {self._auth_key}",
                        "RqUID": str(uuid4()),
                        "User-Agent": USER_AGENT,
                    },
                    data={"scope": self._scope},
                    timeout=self._timeout,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                attempt += 1
                if attempt >= MAX_ATTEMPTS:
                    raise GigaChatError(
                        "GigaChat OAuth request failed after retryable network errors"
                    ) from exc
                await retry_delay(attempt)
                continue

            if self._is_retryable_status(response.status_code):
                attempt += 1
                if attempt < MAX_ATTEMPTS:
                    await retry_delay(attempt, response)
                    continue
            if not 200 <= response.status_code < 300:
                raise GigaChatHTTPError(response.status_code)

            try:
                token_response = _TokenResponse.model_validate(response.json())
            except (ValueError, ValidationError):
                raise LLMResponseError(
                    "GigaChat returned an invalid OAuth response"
                ) from None

            now = time.time()
            provider_expiry = float(token_response.expires_at)
            if provider_expiry > 100_000_000_000:
                provider_expiry /= 1000
            lifetime = max(0.0, provider_expiry - now)
            self._token = token_response.access_token
            self._token_expires_at = now + lifetime * (1 - TOKEN_SAFETY_RATIO)
            return token_response.access_token

    def _token_is_valid(self) -> bool:
        return self._token is not None and time.time() < self._token_expires_at

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code < 600
