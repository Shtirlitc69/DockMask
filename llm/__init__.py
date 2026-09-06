"""Provider-neutral public interface for LLM adapters."""

from llm.base import BaseLLMClient
from llm.catalog import list_llm_models, validate_llm_connection
from llm.factory import get_llm_client, get_provider_specs
from llm.types import (
    LLMClientConfig,
    LLMModelInfo,
    LLMProviderSpec,
    LLMValidationResult,
    ProviderId,
)

__all__ = [
    "BaseLLMClient",
    "LLMClientConfig",
    "LLMModelInfo",
    "LLMProviderSpec",
    "LLMValidationResult",
    "ProviderId",
    "get_llm_client",
    "get_provider_specs",
    "list_llm_models",
    "validate_llm_connection",
]
