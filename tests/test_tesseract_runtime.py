from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from core.extractors.ocr.base import OcrUnavailableError
from core.extractors.ocr.tesseract_provider import _extract_bundled_runtime


def _write_runtime_archive(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("tesseract.exe", b"executable")
        archive.writestr("libcrypto-3-x64.dll", b"isolated")
        archive.writestr("tessdata/rus.traineddata", b"rus")
        archive.writestr("tessdata/eng.traineddata", b"eng")


def test_bundled_runtime_is_extracted_once_and_reused(tmp_path: Path) -> None:
    archive = tmp_path / "runtime.zip"
    _write_runtime_archive(archive)

    first = _extract_bundled_runtime(archive, tmp_path / "cache")
    sentinel = first / "reuse-marker"
    sentinel.write_text("keep", encoding="utf-8")
    second = _extract_bundled_runtime(archive, tmp_path / "cache")

    assert first == second
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert (first / "libcrypto-3-x64.dll").read_bytes() == b"isolated"


@pytest.mark.parametrize(
    "unsafe_name",
    ["../outside.txt", "..\\outside.txt", "/outside.txt", "file.txt:stream"],
)
def test_bundled_runtime_rejects_parent_path_traversal(
    tmp_path: Path, unsafe_name: str
) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(unsafe_name, b"unsafe")

    with pytest.raises(OcrUnavailableError, match="unsafe path"):
        _extract_bundled_runtime(archive, tmp_path / "cache")

    assert not (tmp_path / "outside.txt").exists()


def test_bundled_runtime_rejects_incomplete_archive(tmp_path: Path) -> None:
    archive = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("tesseract.exe", b"executable")

    with pytest.raises(OcrUnavailableError, match="incomplete"):
        _extract_bundled_runtime(archive, tmp_path / "cache")
