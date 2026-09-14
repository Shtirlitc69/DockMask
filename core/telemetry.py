"""Task-local progress and metadata-only diagnostics (never document text or keys)."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime

ProgressCallback = Callable[[str, str, str], Awaitable[None]]
STAGES = ("extract", "detect", "clarify", "redact", "report")


@dataclass
class Trace:
    callback: ProgressCallback | None = None
    events: list[dict] = field(default_factory=list)


current_trace: ContextVar[Trace | None] = ContextVar("pipeline_trace", default=None)


def record(event: str, **metadata: object) -> None:
    trace = current_trace.get()
    if trace is not None:
        trace.events.append({"event": event, "at": datetime.now(UTC).isoformat(), **metadata})


async def progress(stage: str, status: str = "active", detail: str = "") -> None:
    record("progress", stage=stage, status=status, detail=detail)
    trace = current_trace.get()
    if trace is not None and trace.callback is not None:
        await trace.callback(stage, status, detail)
