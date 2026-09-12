"""Task-local generation budgets, shared by detection and role resolution."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from llm.http_utils import LLMProviderError


class LLMRequestBudgetError(LLMProviderError):
    """The job exhausted its allowed generation attempts."""


@dataclass
class RequestBudget:
    limit: int = 64
    used: int = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise LLMRequestBudgetError("LLM generation request budget exhausted")
        self.used += 1


_CURRENT: ContextVar[RequestBudget | None] = ContextVar("llm_request_budget", default=None)


def consume_request() -> None:
    budget = _CURRENT.get()
    if budget is not None:
        budget.consume()


@contextmanager
def request_budget(limit: int = 64):
    """Reset even on cancellation; child tasks share the same mutable counter."""
    if limit <= 0:
        raise ValueError("request budget must be positive")
    budget = RequestBudget(limit)
    token = _CURRENT.set(budget)
    try:
        yield budget
    finally:
        _CURRENT.reset(token)