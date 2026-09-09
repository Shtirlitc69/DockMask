"""Windows desktop entry point: loopback FastAPI plus a WebView2 window."""

from __future__ import annotations

import socket
import ssl
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import uvicorn

from app.main import create_app
from core.config import Settings
from core.extractors.ocr.tesseract_provider import TesseractOcrProvider


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
    try:
        _wait_until_ready(url)
        webview.create_window("DockMask", url=url, width=1280, height=820, min_size=(900, 640))
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
