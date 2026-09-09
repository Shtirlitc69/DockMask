"""OCR provider interface and stable OCR errors."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from core.models import TextBlock


class OcrUnavailableError(RuntimeError):
    """The bundled OCR runtime or language data is unavailable."""


class OcrProcessingError(RuntimeError):
    """Tesseract could not process a document page."""


class OcrProvider(Protocol):
    def extract_page(
        self,
        file_path: str | Path,
        page_number: int,
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> list[TextBlock]: ...
