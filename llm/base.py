"""Provider-agnostic asynchronous LLM contract."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from math import ceil

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
    batch_max_blocks: int = 100
    batch_input_token_limit: int = 12_000
    batch_max_concurrency: int = 4
    provides_inline_roles: bool = False
    provider_name: str = "provider"

    def estimate_input_tokens(self, text: str) -> int:
        """Conservative provider-neutral estimate; adapters may override it."""

        return max(1, ceil(len(text.encode("utf-8")) / 2))

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

    async def find_entities_for_analysis(
        self,
        blocks: Sequence[TextBlock],
        mask_types: Sequence[EntityType],
        auxiliary_types: Sequence[EntityType],
    ) -> dict[str, list[EntitySpan]]:
        """Extract mask and ephemeral auxiliary types without changing legacy clients."""

        requested = tuple(dict.fromkeys((*mask_types, *auxiliary_types)))
        return await self.find_entities_in_blocks(blocks, requested)
