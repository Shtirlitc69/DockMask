"""Safe retry helpers shared by provider transports."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 30.0


class LLMProviderError(RuntimeError):
    """Safe provider failure that contains no response body or secret."""


class LLMHTTPError(LLMProviderError):
    """Safe HTTP status failure."""

    def __init__(self, provider: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"{provider} HTTP request failed with status {status_code}")


class LLMContextLimitError(LLMProviderError):
    """The provider rejected a prompt because it exceeded its context window."""


_CONTEXT_ERROR_CODES = {
    "context_length_exceeded",
    "context_window_exceeded",
    "max_tokens_exceeded",
    "prompt_too_long",
    "tokens_limit_exceeded",
}
_CONTEXT_ERROR_PHRASES = (
    "context length",
    "context window",
    "maximum context",
    "prompt is too long",
    "prompt too long",
    "too many tokens",
    "превышен размер контекста",
    "слишком длинный промпт",
)


def is_context_limit_response(response: httpx.Response) -> bool:
    """Recognize context overflow without exposing the provider response body."""

    if response.status_code == 413:
        return True
    if response.status_code not in (400, 422):
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error", payload)
    values: list[str] = []
    if isinstance(error, dict):
        values.extend(
            value
            for key in ("code", "type", "message")
            if isinstance((value := error.get(key)), str)
        )
    elif isinstance(error, str):
        values.append(error)
    normalized = " ".join(values).casefold()
    return any(value.casefold() in _CONTEXT_ERROR_CODES for value in values) or any(
        phrase in normalized for phrase in _CONTEXT_ERROR_PHRASES
    )


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None or not (value := response.headers.get("Retry-After")):
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return max(0.0, (parsed - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


async def retry_delay(
    attempt: int,
    response: httpx.Response | None = None,
) -> None:
    """Wait before a retry while honoring a bounded Retry-After value."""

    delay = RETRY_BASE_DELAY_SECONDS * (2 ** max(0, attempt - 1))
    retry_after = _retry_after_seconds(response)
    if retry_after is not None:
        delay = max(delay, retry_after)
    delay = min(delay, RETRY_MAX_DELAY_SECONDS) + random.uniform(0.0, 0.25)
    await asyncio.sleep(delay)


async def request_with_retries(
    provider: str,
    request: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Retry network errors, 429, and 5xx up to three total attempts."""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        response: httpx.Response | None = None
        try:
            response = await request()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise LLMProviderError(
                    f"{provider} request failed after retryable network errors"
                ) from exc
        else:
            if is_context_limit_response(response):
                raise LLMContextLimitError(
                    f"{provider} request exceeded the model context limit"
                )
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == MAX_ATTEMPTS:
                if not 200 <= response.status_code < 300:
                    raise LLMHTTPError(provider, response.status_code)
                return response
        await retry_delay(attempt, response)
    raise AssertionError("retry loop terminated unexpectedly")
