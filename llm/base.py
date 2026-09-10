"""Provider-agnostic asynchronous LLM contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from core.models import EntitySpan, EntityType, PartyRole, TextBlock


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

    batch_max_chars: int = 0
    batch_max_concurrency: int = 4
    provides_inline_roles: bool = False
    provider_name: str = "provider"

    async def find_entities_in_blocks(
        self,
        blocks: Sequence[TextBlock],
        types: Sequence[EntityType],
    ) -> dict[str, list[EntitySpan]]:
        """Analyze several blocks, falling back to the single-block contract."""

        result: dict[str, list[EntitySpan]] = {}
        for block in blocks:
            result[block.block_id] = await self.find_entities(block.text, types)
        return result
