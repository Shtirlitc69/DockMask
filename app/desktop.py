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
from typing import Any, ClassVar
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID, uuid4

import uvicorn

from app.logging_config import configure_file_logging
from app.main import create_app
from core.config import Settings
from core.extractors.ocr.tesseract_provider import TesseractOcrProvider

LOGGER = logging.getLogger("dockmask.desktop")

# Cold starts inside a frozen onefile build (extraction plus antivirus scans
# plus the uvicorn lifespan wiring database, keyring and OCR) routinely exceed
# the previous 20 second budget on slower machines.
API_READY_TIMEOUT_SECONDS = 60.0

LOADING_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>DockMask</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { background: #0f172a; color: #e2e8f0; font-family: "Segoe UI", Arial, sans-serif; }
  .wrap { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; }
  .spinner { width: 44px; height: 44px; border: 4px solid #334155; border-top-color: #38bdf8; border-radius: 50%; animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  h1 { font-size: 20px; font-weight: 600; margin: 0; }
  p { margin: 0; color: #94a3b8; font-size: 13px; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="spinner"></div>
    <h1>DockMask</h1>
    <p>Запуск локального сервера…</p>
  </div>
</body>
</html>
"""

ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>DockMask — ошибка запуска</title>
<style>
  html, body { height: 100%; margin: 0; }
  body { background: #0f172a; color: #e2e8f0; font-family: "Segoe UI", Arial, sans-serif; display: flex; align-items: center; justify-content: center; }
  .card { max-width: 480px; padding: 32px; }
  h1 { font-size: 18px; margin: 0 0 12px; }
  code { color: #fca5a5; font-size: 12px; word-break: break-all; }
  p { color: #94a3b8; font-size: 13px; line-height: 1.5; }
</style>
</head>
<body>
  <div class="card">
    <h1>Не удалось запустить локальный сервер</h1>
    <p>Проверьте, что приложение не блокируется антивирусом, и повторите запуск.</p>
    <p>Подробности в журнале:<br><code>{log_file}</code></p>
  </div>
</body>
</html>
"""


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


def _wait_until_ready(url: str, timeout_seconds: float = API_READY_TIMEOUT_SECONDS) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError("local_api_start_failed")


def _error_html(log_file: Path | None) -> str:
    location = str(log_file) if log_file is not None else "журнал недоступен"
    return ERROR_HTML_TEMPLATE.replace("{log_file}", location)


def _message_box(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x00000010)
    except Exception:
        LOGGER.exception("desktop_startup stage=message_box_failed")


def _activate(window: Any, url: str, started: float, log_file: Path | None) -> None:
    """Wait for the API in a pywebview worker thread, then swap in the UI."""
    try:
        _wait_until_ready(url)
    except RuntimeError:
        LOGGER.error(
            "desktop_startup stage=api_start_failed seconds=%.3f",
            time.monotonic() - started,
        )
        window.load_html(_error_html(log_file))
        return
    LOGGER.info("desktop_startup stage=api_ready seconds=%.3f", time.monotonic() - started)
    window.load_url(url)


def main() -> None:
    started = time.monotonic()
    settings = Settings(env="production")
    # File logging must exist before anything else can fail; the uvicorn
    # lifespan only configures it after the API is already serving.
    try:
        log_file = configure_file_logging(settings.logs_path)
    except OSError:
        log_file = None
        LOGGER.exception("desktop_startup stage=file_logging_unavailable")
    LOGGER.info("desktop_startup stage=boot seconds=%.3f", time.monotonic() - started)
    import webview

    application = create_app(settings=settings)
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
    LOGGER.info("desktop_startup stage=api_thread seconds=%.3f", time.monotonic() - started)

    # The window is shown immediately with a loading page so that the OS keeps
    # pumping messages and the user gets visual feedback while the backend and
    # the frozen runtime warm up.
    desktop_api = DesktopApi(url)
    window = webview.create_window(
        "DockMask",
        html=LOADING_HTML,
        js_api=desktop_api,
        width=1280,
        height=820,
        min_size=(900, 640),
    )
    desktop_api.window = window
    window.events.loaded += lambda: LOGGER.info(
        "desktop_startup stage=window_loaded seconds=%.3f", time.monotonic() - started
    )
    LOGGER.info("desktop_startup stage=window_created seconds=%.3f", time.monotonic() - started)
    try:
        webview.start(_activate, args=(window, url, started, log_file))
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
    try:
        main()
    except Exception:
        LOGGER.exception("desktop_startup stage=fatal")
        _message_box(
            "DockMask",
            "Приложению не удалось запуститься. Подробности — в журнале "
            "dockmask.log внутри папки данных DockMask.",
        )
        raise