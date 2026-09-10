"""Windows desktop entry point: loopback FastAPI plus a WebView2 window."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import ssl
import sys
import threading
import time
from pathlib import Path, PurePath
from typing import ClassVar
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID, uuid4

import uvicorn

from app.main import create_app
from core.config import Settings
from core.extractors.ocr.tesseract_provider import TesseractOcrProvider


class DesktopApi:
    """Minimal native bridge for saving artifacts through a Windows dialog."""

    _REPORT_EXTENSIONS: ClassVar[dict[str, str]] = {
        "json": ".json",
        "csv": ".csv",
        "xlsx": ".xlsx",
    }

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self.window = None

    def save_artifact(
        self,
        job_id: str,
        kind: str,
        suggested_filename: str,
    ) -> dict[str, str]:
        try:
            UUID(job_id)
        except (ValueError, TypeError, AttributeError):
            return {"status": "error", "code": "invalid_job_id"}
        if kind not in {"document", *self._REPORT_EXTENSIONS}:
            return {"status": "error", "code": "invalid_artifact"}
        safe_name = PurePath(str(suggested_filename).replace("\\", "/")).name
        suffix = Path(safe_name).suffix.casefold()
        allowed_suffixes = {".pdf", ".docx", ".xlsx"} if kind == "document" else {
            self._REPORT_EXTENSIONS[kind]
        }
        if not safe_name or suffix not in allowed_suffixes or self.window is None:
            return {"status": "error", "code": "invalid_filename"}

        from webview import FileDialog

        label = suffix.removeprefix(".").upper()
        selected = self.window.create_file_dialog(
            FileDialog.SAVE,
            save_filename=safe_name,
            file_types=(f"{label} (*{suffix})",),
        )
        if not selected:
            return {"status": "cancelled"}

        target = Path(selected[0])
        if target.suffix.casefold() != suffix:
            target = target.with_suffix(suffix)
        endpoint = {
            "document": "document",
            "json": "report.json",
            "csv": "report.csv",
            "xlsx": "report.xlsx",
        }[kind]
        temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        try:
            with urlopen(
                f"{self._base_url}/api/jobs/{job_id}/{endpoint}",
                timeout=60,
            ) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            os.replace(temporary, target)
        except (OSError, URLError):
            temporary.unlink(missing_ok=True)
            return {"status": "error", "code": "save_failed"}
        return {"status": "saved", "filename": target.name}


def _wait_until_ready(url: str, timeout_seconds: float = 20) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError("local_api_start_failed")


def main() -> None:
    started = time.monotonic()
    logger = logging.getLogger("uvicorn.error")
    import webview

    application = create_app(settings=Settings(env="production"))
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="info")
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        name="dockmask-api",
        daemon=True,
    )
    thread.start()
    logger.info("desktop_startup stage=api_thread seconds=%.3f", time.monotonic() - started)
    try:
        _wait_until_ready(url)
        logger.info("desktop_startup stage=api_ready seconds=%.3f", time.monotonic() - started)
        desktop_api = DesktopApi(url)
        window = webview.create_window(
            "DockMask",
            url=url,
            js_api=desktop_api,
            width=1280,
            height=820,
            min_size=(900, 640),
        )
        desktop_api.window = window
        window.events.loaded += lambda: logger.info(
            "desktop_startup stage=window_loaded seconds=%.3f", time.monotonic() - started
        )
        webview.start()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()


def _self_test() -> int:
    ssl.create_default_context()
    provider = TesseractOcrProvider()
    provider.check_runtime()
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(_self_test())
    main()
