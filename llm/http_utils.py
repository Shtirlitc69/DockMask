"""Safe retry helpers shared by provider transports."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable

import httpx

MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 0.1
MAX_RETRY_DELAY_SECONDS = 5.0
RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})
FAIL_FAST_ERROR_LIMIT = 6
FAIL_FAST_WINDOW_SECONDS = 30.0
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 20.0
LOGGER = logging.getLogger(__name__)


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
    """Retry transient failures and apply fail-fast protections."""

    tracker = _CircuitBreakerState.get(provider)
    tracker.ensure_closed()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await request()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            tracker.record_failure()
            if attempt == MAX_ATTEMPTS:
                raise LLMProviderError(
                    f"{provider} request failed after retryable network errors"
                ) from exc
        else:
            retryable = _is_retryable_status(response.status_code)
            if not retryable or attempt == MAX_ATTEMPTS:
                if not 200 <= response.status_code < 300:
                    tracker.record_failure()
                    raise LLMHTTPError(provider, response.status_code)
                tracker.record_success()
                return response
            tracker.record_failure()
            await _sleep_with_backoff(attempt, response.headers.get("Retry-After"))
            _log_retry(provider, response.status_code, attempt)
            continue
        await _sleep_with_backoff(attempt, None)
        _log_retry(provider, None, attempt)
    raise AssertionError("retry loop terminated unexpectedly")


def _is_retryable_status(status_code: int) -> bool:
    return status_code in RETRYABLE_STATUSES


def _log_retry(provider: str, status_code: int | None, attempt: int) -> None:
    if status_code in RETRYABLE_STATUSES:
        LOGGER.warning(
            "%s transient HTTP %s, retrying attempt %s/%s",
            provider,
            status_code,
            attempt + 1,
            MAX_ATTEMPTS,
        )
    else:
        LOGGER.debug(
            "%s transient network error, retrying attempt %s/%s",
            provider,
            attempt + 1,
            MAX_ATTEMPTS,
        )


async def _sleep_with_backoff(attempt: int, retry_after: str | None) -> None:
    header_delay = _parse_retry_after(retry_after)
    if header_delay is not None:
        await asyncio.sleep(header_delay)
        return
    exp_delay = min(MAX_RETRY_DELAY_SECONDS, RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    jitter = random.uniform(0, exp_delay * 0.2)
    await asyncio.sleep(exp_delay + jitter)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    if seconds <= 0:
        return None
    return min(seconds, MAX_RETRY_DELAY_SECONDS)


class _CircuitBreakerState:
    _states: dict[str, "_CircuitBreakerState"] = {}

    def __init__(self) -> None:
        self._failures: list[float] = []
        self._open_until = 0.0

    @classmethod
    def get(cls, provider: str) -> "_CircuitBreakerState":
        state = cls._states.get(provider)
        if state is None:
            state = cls._states[provider] = _CircuitBreakerState()
        return state

    def ensure_closed(self) -> None:
        if time.monotonic() < self._open_until:
            raise LLMProviderError("provider circuit breaker is open due to repeated failures")

    def record_success(self) -> None:
        self._failures.clear()
        self._open_until = 0.0

    def record_failure(self) -> None:
        now = time.monotonic()
        window_start = now - FAIL_FAST_WINDOW_SECONDS
        self._failures = [ts for ts in self._failures if ts >= window_start]
        self._failures.append(now)
        if len(self._failures) >= FAIL_FAST_ERROR_LIMIT:
            self._open_until = now + CIRCUIT_BREAKER_COOLDOWN_SECONDS
