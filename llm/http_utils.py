"""Safe retry helpers shared by provider transports."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import httpx

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.1


class LLMProviderError(RuntimeError):
    """Safe provider failure that contains no response body or secret."""


class LLMHTTPError(LLMProviderError):
    """Safe HTTP status failure."""

    def __init__(self, provider: str, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"{provider} HTTP request failed with status {status_code}")


async def request_with_retries(
    provider: str,
    request: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Retry network errors, 429, and 5xx up to three total attempts."""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await request()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise LLMProviderError(
                    f"{provider} request failed after retryable network errors"
                ) from exc
        else:
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == MAX_ATTEMPTS:
                if not 200 <= response.status_code < 300:
                    raise LLMHTTPError(provider, response.status_code)
                return response
        await asyncio.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    raise AssertionError("retry loop terminated unexpectedly")
