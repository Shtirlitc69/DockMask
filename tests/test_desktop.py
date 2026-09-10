import io
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from uuid import uuid4

from app.desktop import DesktopApi


def _api_with_window(selection: tuple[str, ...] | None) -> DesktopApi:
    api = DesktopApi("http://127.0.0.1:12345")
    api.window = MagicMock()
    api.window.create_file_dialog.return_value = selection
    return api


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
