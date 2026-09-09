"""Privacy-safe rotating application logs stored beside local app data."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "dockmask.log"
MAX_LOG_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3


def configure_file_logging(log_directory: str | Path) -> Path:
    """Attach one rotating technical log handler and return its file path.

    Callers must log only event identifiers and safe machine codes. Document
    text, entity values, prompts, API keys, OAuth tokens and provider response
    bodies are deliberately outside this logging contract.
    """

    directory = Path(log_directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / LOG_FILENAME
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_dockmask_handler", False):
            root.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(
        target,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler._dockmask_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)
    return target
