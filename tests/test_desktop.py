import io
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from uuid import uuid4

import pytest

from app.desktop import (
    DesktopApi,
    StartupError,
    _activate,
    _error_html,
    _run_desktop,
    _wait_until_ready,
    main,
)


def _api_with_window(selection: tuple[str, ...] | None) -> DesktopApi:
    api = DesktopApi("http://127.0.0.1:12345")
    window = MagicMock()
    window.create_file_dialog.return_value = selection
    api._bind_window(window)
    return api


def test_native_bridge_exposes_only_save_artifact() -> None:
    api = DesktopApi("http://127.0.0.1:12345")

    public_members = [name for name in dir(api) if not name.startswith("_")]

    assert public_members == ["save_artifact"]
    assert not hasattr(api, "window")


def test_native_save_uses_dialog_and_atomically_writes_artifact(tmp_path: Path) -> None:
    target = tmp_path / "договор_обезличенный.docx"
    api = _api_with_window((str(target),))

    with patch("app.desktop.urlopen", return_value=io.BytesIO(b"document")) as request:
        result = api.save_artifact(str(uuid4()), "document", target.name)

    assert result == {"status": "saved", "filename": target.name}
    assert target.read_bytes() == b"document"
    assert "/document" in request.call_args.args[0]
    assert list(tmp_path.glob("*.tmp")) == []


def test_native_save_cancel_and_validation_do_not_download(tmp_path: Path) -> None:
    api = _api_with_window(None)
    with patch("app.desktop.urlopen") as request:
        assert api.save_artifact(str(uuid4()), "csv", "отчёт.csv") == {
            "status": "cancelled"
        }
        assert api.save_artifact("not-a-uuid", "csv", "отчёт.csv")["status"] == "error"
    request.assert_not_called()


def test_native_save_failure_leaves_no_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "отчёт.json"
    api = _api_with_window((str(target),))
    with patch("app.desktop.urlopen", side_effect=URLError("offline")):
        result = api.save_artifact(str(uuid4()), "json", target.name)

    assert result == {"status": "error", "code": "save_failed"}
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_wait_until_ready_returns_after_successful_health_check() -> None:
    response = MagicMock(status=200)
    response.__enter__.return_value = response
    backend_thread = MagicMock(spec=threading.Thread)
    backend_thread.is_alive.return_value = True

    with patch("app.desktop.urlopen", return_value=response) as request:
        _wait_until_ready("http://127.0.0.1:12345", backend_thread, timeout_seconds=1)

    request.assert_called_once_with("http://127.0.0.1:12345/api/health", timeout=1)


def test_wait_until_ready_fails_immediately_when_backend_stops() -> None:
    backend_thread = MagicMock(spec=threading.Thread)
    backend_thread.is_alive.return_value = False

    with patch("app.desktop.urlopen") as request, pytest.raises(StartupError) as error:
        _wait_until_ready("http://127.0.0.1:12345", backend_thread)

    assert error.value.code == "backend_failed"
    request.assert_not_called()


def test_wait_until_ready_reports_timeout() -> None:
    with pytest.raises(StartupError) as error:
        _wait_until_ready("http://127.0.0.1:12345", timeout_seconds=0)

    assert error.value.code == "startup_timeout"


def test_error_html_escapes_log_path() -> None:
    rendered = _error_html(Path("C:/Users/A&B/<logs>/dockmask.log"), "startup_timeout")

    assert "A&amp;B" in rendered
    assert "&lt;logs&gt;" in rendered
    assert "слишком много времени" in rendered


def test_activate_loads_application_after_backend_is_ready() -> None:
    window = MagicMock()
    thread = MagicMock(spec=threading.Thread)
    server = MagicMock()

    with patch("app.desktop._wait_until_ready") as wait:
        _activate(window, "http://127.0.0.1:12345", 0, None, thread, server)

    wait.assert_called_once_with("http://127.0.0.1:12345", thread)
    window.load_url.assert_called_once_with("http://127.0.0.1:12345")
    window.load_html.assert_not_called()


def test_activate_stops_server_and_shows_backend_failure() -> None:
    window = MagicMock()
    thread = MagicMock(spec=threading.Thread)
    server = MagicMock(should_exit=False)

    with patch("app.desktop._wait_until_ready", side_effect=StartupError("backend_failed")):
        _activate(window, "http://127.0.0.1:12345", 0, None, thread, server)

    assert server.should_exit is True
    assert "завершился во время запуска" in window.load_html.call_args.args[0]
    window.load_url.assert_not_called()


def test_activate_reports_ui_load_failure() -> None:
    window = MagicMock()
    window.load_url.side_effect = RuntimeError("webview unavailable")
    thread = MagicMock(spec=threading.Thread)
    server = MagicMock(should_exit=False)

    with patch("app.desktop._wait_until_ready"):
        _activate(window, "http://127.0.0.1:12345", 0, None, thread, server)

    assert server.should_exit is True
    assert "интерфейс приложения" in window.load_html.call_args.args[0]


def test_desktop_entrypoint_handles_fatal_error_without_reraising() -> None:
    with (
        patch("app.desktop.main", side_effect=RuntimeError("boom")),
        patch("app.desktop._message_box") as message_box,
    ):
        exit_code = _run_desktop()

    assert exit_code == 1
    message_box.assert_called_once()


def test_main_configures_fallback_logging_before_settings_validation(tmp_path: Path) -> None:
    fallback = tmp_path / "dockmask.log"

    with (
        patch("app.desktop._configure_startup_logging", return_value=fallback) as configure,
        patch("app.desktop.Settings", side_effect=ValueError("invalid settings")),
        pytest.raises(ValueError, match="invalid settings"),
    ):
        main()

    configure.assert_called_once_with()


def test_main_cleans_up_backend_when_window_creation_fails(tmp_path: Path) -> None:
    settings = MagicMock(logs_path=tmp_path)
    listener = MagicMock()
    listener.getsockname.return_value = ("127.0.0.1", 12345)
    server = MagicMock(should_exit=False)
    thread = MagicMock(spec=threading.Thread)
    thread.is_alive.return_value = False

    with (
        patch("app.desktop._configure_startup_logging", return_value=tmp_path / "dockmask.log"),
        patch("app.desktop.Settings", return_value=settings),
        patch("app.main.create_app"),
        patch("app.desktop.socket.socket", return_value=listener),
        patch("app.desktop.uvicorn.Config"),
        patch("app.desktop.uvicorn.Server", return_value=server),
        patch("app.desktop.threading.Thread", return_value=thread),
        patch("webview.create_window", side_effect=RuntimeError("window failed")),
        pytest.raises(RuntimeError, match="window failed"),
    ):
        main()

    assert server.should_exit is True
    thread.start.assert_called_once_with()
    thread.join.assert_called_once_with(timeout=10)
    listener.close.assert_called_once_with()
