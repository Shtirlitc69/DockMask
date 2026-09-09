"""Provider-independent model discovery and synthetic validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from llm.factory import get_llm_client
from llm.http_utils import LLMHTTPError, LLMProviderError
from llm.structured import LLMResponseError
from llm.types import LLMClientConfig, LLMModelInfo, LLMValidationResult


@runtime_checkable
class SupportsModelListing(Protocol):
    async def list_models(self) -> list[LLMModelInfo]: ...


async def list_llm_models(
    config: LLMClientConfig,
    http_client: httpx.AsyncClient | None,
) -> list[LLMModelInfo]:
    """Return normalized models without depending on FastAPI or persistence."""

    client = get_llm_client(config, http_client)
    if not isinstance(client, SupportsModelListing):
        return [LLMModelInfo(id=config.model, display_name=config.model)]
    return await client.list_models()


async def validate_llm_connection(
    config: LLMClientConfig,
    http_client: httpx.AsyncClient | None,
) -> LLMValidationResult:
    """Run a small synthetic structured request and return a safe result."""

    try:
        client = get_llm_client(config, http_client)
        await client.classify_party(
            "Поставщик Тестовая Компания заключил договор.",
            "Тестовая Компания",
        )
    except ValueError:
        return LLMValidationResult(
            False,
            "invalid_configuration",
            "Invalid LLM configuration",
        )
    except LLMHTTPError as exc:
        if exc.status_code in {401, 403}:
            code = "authentication_failed"
        elif exc.status_code == 404:
            code = "model_not_found"
        else:
            code = "provider_error"
        return LLMValidationResult(False, code, "LLM connection validation failed")
    except (LLMProviderError, httpx.HTTPError):
        return LLMValidationResult(False, "connection_failed", "LLM connection failed")
    except LLMResponseError:
        return LLMValidationResult(
            False,
            "unsupported_model_capability",
            "The selected model did not return structured output",
        )
    return LLMValidationResult(True, "ok", "LLM connection validated")
