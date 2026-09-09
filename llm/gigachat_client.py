"""Asynchronous GigaChat adapter with OAuth token caching."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Self
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from core.models import EntitySpan, EntityType, PartyRole
from llm.base import BaseLLMClient
from llm.http_utils import LLMHTTPError, LLMProviderError
from llm.prompts import (
    ENTITY_SYSTEM_PROMPT,
    PARTY_SYSTEM_PROMPT,
    ROLE_RESPONSE_SCHEMA,
    build_entity_prompt,
    build_party_prompt,
    entity_response_schema,
)
from llm.structured import (
    EntitiesResponse,
    LLMResponseError,
    RoleResponse,
    parse_model_json,
    to_entity_spans,
)
from llm.types import LLMModelInfo

LOGGER = logging.getLogger(__name__)
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
MODELS_PATH = "/v1/models"
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.1
TOKEN_SAFETY_RATIO = 0.1
GIGACHAT_SOURCE = "gigachat"
GIGACHAT_CONFIDENCE = 0.8
USER_AGENT = "DockMask/0.1"


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


class _ChatResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    choices: list[_ChatChoice]


class GigaChatClient(BaseLLMClient):
    """Call GigaChat through an injected or internally owned HTTP client."""

    def __init__(
        self,
        auth_key: str,
        scope: str,
        model: str,
        http_client: httpx.AsyncClient | None,
        oauth_url: str,
        base_url: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not auth_key:
            raise ValueError("auth_key must not be empty")
        if not scope or not model or not oauth_url or not base_url:
            raise ValueError("GigaChat configuration values must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

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

    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        requested = frozenset(types)
        if not text or not requested:
            return []

        content = await self._complete(
            build_entity_prompt(text, requested),
            response_schema=entity_response_schema(requested),
            system_prompt=ENTITY_SYSTEM_PROMPT,
        )
        payload = parse_model_json(content, EntitiesResponse)
        return to_entity_spans(
            text,
            requested,
            payload.entities,
            source=GIGACHAT_SOURCE,
            confidence=GIGACHAT_CONFIDENCE,
            logger=LOGGER,
        )

    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        if not context_snippet or not candidate_name:
            return None

        content = await self._complete(
            build_party_prompt(context_snippet, candidate_name),
            response_schema=ROLE_RESPONSE_SCHEMA,
            system_prompt=PARTY_SYSTEM_PROMPT,
        )
        role = PartyRole(parse_model_json(content, RoleResponse).role)
        return None if role is PartyRole.UNKNOWN else role

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
                await self._retry_delay(attempt)
                continue
            if response.status_code == 401 and not refreshed_after_401:
                refreshed_after_401 = True
                token = await self._refresh_rejected_token(token)
                continue
            if self._is_retryable_status(response.status_code):
                attempt += 1
                if attempt < MAX_ATTEMPTS:
                    await self._retry_delay(attempt)
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "schema": response_schema,
                "strict": True,
            },
        }
        transient_attempt = 0
        refreshed_after_401 = False
        token = await self._get_token()

        while True:
            try:
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
                await self._retry_delay(transient_attempt)
                continue

            if response.status_code == 401 and not refreshed_after_401:
                refreshed_after_401 = True
                token = await self._refresh_rejected_token(token)
                continue
            if self._is_retryable_status(response.status_code):
                transient_attempt += 1
                if transient_attempt < MAX_ATTEMPTS:
                    await self._retry_delay(transient_attempt)
                    continue
            if not 200 <= response.status_code < 300:
                raise GigaChatHTTPError(response.status_code)

            try:
                envelope = _ChatResponse.model_validate(response.json())
                return envelope.choices[0].message.content
            except (ValueError, ValidationError, IndexError):
                raise LLMResponseError(
                    "GigaChat returned an invalid chat response"
                ) from None

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
                await self._retry_delay(attempt)
                continue

            if self._is_retryable_status(response.status_code):
                attempt += 1
                if attempt < MAX_ATTEMPTS:
                    await self._retry_delay(attempt)
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

    @staticmethod
    async def _retry_delay(attempt: int) -> None:
        await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
