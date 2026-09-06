"""Provider-neutral configuration and discovery models for the LLM layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit


class ProviderId(StrEnum):
    """Stable identifiers shared with future configuration and UI layers."""

    MOCK = "mock"
    GIGACHAT = "gigachat"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"
    OLLAMA = "ollama"
    VLLM = "vllm"


@dataclass(frozen=True, slots=True)
class LLMClientConfig:
    """Resolved values needed to construct one LLM adapter.

    The application layer remains responsible for loading and storing these
    values.  This object deliberately performs no environment or secret-store
    access.
    """

    provider: ProviderId | str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    oauth_url: str | None = None
    scope: str | None = None
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class LLMModelInfo:
    """Normalized model information returned by any provider."""

    id: str
    display_name: str
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LLMProviderSpec:
    """Static integration metadata for application and presentation layers."""

    id: ProviderId
    display_name: str
    requires_api_key: bool
    requires_base_url: bool
    default_base_url: str | None = None
    supports_model_listing: bool = True
    development_only: bool = False


@dataclass(frozen=True, slots=True)
class LLMValidationResult:
    """Safe result of a synthetic provider connectivity check."""

    ok: bool
    code: str
    message: str


def validate_user_base_url(url: str) -> str:
    """Return a normalized safe URL for local or HTTPS provider endpoints."""

    candidate = url.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain credentials, query, or fragment")
    if parsed.scheme == "http" and parsed.hostname.casefold() not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("plain HTTP is allowed only for loopback addresses")
    return candidate
