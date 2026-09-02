"""Provider-agnostic asynchronous LLM contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from core.models import EntitySpan, EntityType, PartyRole


class BaseLLMClient(ABC):
    """Interface implemented by mock, cloud, and local LLM providers."""

    @abstractmethod
    async def find_entities(
        self,
        text: str,
        types: Sequence[EntityType],
    ) -> list[EntitySpan]:
        """Return exact entity spans for the requested LLM-backed types."""

    @abstractmethod
    async def classify_party(
        self,
        context_snippet: str,
        candidate_name: str,
    ) -> PartyRole | None:
        """Return the candidate's document role or ``None`` if uncertain."""
