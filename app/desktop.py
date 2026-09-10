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
from html import escape
from pathlib import Path, PurePath
from typing import Any, ClassVar
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID, uuid4

import uvicorn
from platformdirs import user_data_path

from app.logging_config import configure_file_logging
from core.config import Settings
from core.extractors.ocr.tesseract_provider import TesseractOcrProvider

LOGGER = logging.getLogger("dockmask.desktop")

# Cold starts inside a frozen onefile build (extraction plus antivirus scans
# plus the uvicorn lifespan wiring database, keyring and OCR) routinely exceed
# the previous 20 second budget on slower machines.
API_READY_TIMEOUT_SECONDS = 60.0
API_READY_INITIAL_DELAY_SECONDS = 0.1
API_READY_MAX_DELAY_SECONDS = 0.5

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
    <p>{message}</p>
    <p>Подробности в журнале:<br><code>{log_file}</code></p>
  </div>
</body>
</html>
"""

STARTUP_ERROR_MESSAGES = {
    "backend_failed": "Локальный сервер завершился во время запуска. Повторите запуск приложения.",
    "startup_timeout": "Запуск занял слишком много времени. Повторите попытку после перезагрузки Windows.",
    "ui_load_failed": "Сервер запущен, но интерфейс приложения не удалось открыть.",
}


class StartupError(RuntimeError):
    """A user-visible desktop startup failure with a stable machine code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DesktopApi:
    """Minimal native bridge for saving artifacts through a Windows dialog."""

    _REPORT_EXTENSIONS: ClassVar[dict[str, str]] = {
        "json": ".json",
        "csv": ".csv",
        "xlsx": ".xlsx",
    }

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        # pywebview recursively exposes every public js_api attribute. Keeping
        # its native Window private prevents traversal into WinForms/WebView2
        # COM objects from the bridge worker thread.
        self._window: Any | None = None

    def _bind_window(self, window: Any) -> None:
        self._window = window

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
        if not safe_name or suffix not in allowed_suffixes or self._window is None:
            return {"status": "error", "code": "invalid_filename"}

        from webview import FileDialog

        label = suffix.removeprefix(".").upper()
        selected = self._window.create_file_dialog(
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


def _wait_until_ready(
    url: str,
    backend_thread: threading.Thread | None = None,
    timeout_seconds: float = API_READY_TIMEOUT_SECONDS,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    delay = API_READY_INITIAL_DELAY_SECONDS
    while time.monotonic() < deadline:
        if backend_thread is not None and not backend_thread.is_alive():
            raise StartupError("backend_failed")
        try:
            with urlopen(f"{url}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(delay, remaining))
            delay = min(delay * 1.5, API_READY_MAX_DELAY_SECONDS)
    if backend_thread is not None and not backend_thread.is_alive():
        raise StartupError("backend_failed")
    raise StartupError("startup_timeout")


def _error_html(log_file: Path | None, code: str) -> str:
    location = escape(str(log_file) if log_file is not None else "журнал недоступен")
    message = escape(STARTUP_ERROR_MESSAGES.get(code, STARTUP_ERROR_MESSAGES["backend_failed"]))
    return ERROR_HTML_TEMPLATE.replace("{message}", message).replace("{log_file}", location)


def _configure_startup_logging() -> Path | None:
    """Create a fallback log before environment-backed settings are validated."""
    fallback_logs = user_data_path("DockMask", "Triema", ensure_exists=False) / "logs"
    try:
        return configure_file_logging(fallback_logs)
    except OSError:
        return None


def _message_box(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, title, 0x00000010)
    except Exception:
        LOGGER.exception("desktop_startup stage=message_box_failed")


def _show_startup_error(window: Any, log_file: Path | None, code: str) -> None:
    try:
        window.load_html(_error_html(log_file, code))
    except Exception:
        LOGGER.exception("desktop_startup stage=error_page_failed code=%s", code)


def _activate(
    window: Any,
    url: str,
    started: float,
    log_file: Path | None,
    backend_thread: threading.Thread,
    server: uvicorn.Server,
) -> None:
    """Wait for the API in a pywebview worker thread, then swap in the UI."""
    try:
        _wait_until_ready(url, backend_thread)
    except StartupError as error:
        LOGGER.error(
            "desktop_startup stage=%s seconds=%.3f",
            error.code,
            time.monotonic() - started,
        )
        server.should_exit = True
        _show_startup_error(window, log_file, error.code)
        return
    LOGGER.info("desktop_startup stage=api_ready seconds=%.3f", time.monotonic() - started)
    try:
        window.load_url(url)
    except Exception:
        LOGGER.exception(
            "desktop_startup stage=ui_load_failed seconds=%.3f",
            time.monotonic() - started,
        )
        server.should_exit = True
        _show_startup_error(window, log_file, "ui_load_failed")


def _run_server(server: uvicorn.Server, listener: socket.socket) -> None:
    try:
        server.run(sockets=[listener])
    except BaseException:
        LOGGER.exception("desktop_startup stage=backend_crashed")


def main() -> None:
    started = time.monotonic()
    log_file = _configure_startup_logging()
    settings = Settings(env="production")
    if log_file is None or log_file.parent != settings.logs_path:
        try:
            log_file = configure_file_logging(settings.logs_path)
        except OSError:
            LOGGER.exception("desktop_startup stage=file_logging_unavailable")
    LOGGER.info("desktop_startup stage=boot seconds=%.3f", time.monotonic() - started)
    import webview

    from app.main import create_app

    listener: socket.socket | None = None
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    try:
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
            target=_run_server,
            args=(server, listener),
            name="dockmask-api",
            daemon=True,
        )
        thread.start()
        LOGGER.info("desktop_startup stage=api_thread seconds=%.3f", time.monotonic() - started)

        # Show the window immediately so Windows can pump messages while the
        # frozen runtime and backend finish warming up.
        desktop_api = DesktopApi(url)
        window = webview.create_window(
            "DockMask",
            html=LOADING_HTML,
            js_api=desktop_api,
            width=1280,
            height=820,
            min_size=(900, 640),
        )
        desktop_api._bind_window(window)
        window.events.loaded += lambda: LOGGER.info(
            "desktop_startup stage=window_loaded seconds=%.3f", time.monotonic() - started
        )
        LOGGER.info(
            "desktop_startup stage=window_created seconds=%.3f", time.monotonic() - started
        )
        webview.start(
            _activate,
            args=(window, url, started, log_file, thread, server),
        )
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
            if thread.is_alive():
                LOGGER.warning("desktop_shutdown stage=backend_join_timeout")
        if listener is not None:
            listener.close()


def _self_test() -> int:
    ssl.create_default_context()
    provider = TesseractOcrProvider()
    provider.check_runtime()
    return 0


def _run_desktop() -> int:
    try:
        main()
    except Exception:
        LOGGER.exception("desktop_startup stage=fatal")
        _message_box(
            "DockMask",
            "Приложению не удалось запуститься. Подробности — в журнале "
            "dockmask.log внутри папки данных DockMask.",
        )
        return 1
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv[1:]:
        raise SystemExit(_self_test())
    raise SystemExit(_run_desktop())
