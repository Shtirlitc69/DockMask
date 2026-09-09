"""Local Tesseract OCR provider used in development and in the packaged EXE."""

from __future__ import annotations

import csv
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from uuid import uuid4

import fitz
from platformdirs import user_cache_path

from core.extractors.ocr.base import OcrProcessingError, OcrUnavailableError
from core.models import BlockKind, Location, TextBlock

logger = logging.getLogger(__name__)
_ARCHIVE_NAME = "dockmask-tesseract-runtime.zip"
_HASH_MARKER = ".dockmask-runtime.sha256"
_REQUIRED_RUNTIME_FILES = (
    Path("tesseract.exe"),
    Path("tessdata/rus.traineddata"),
    Path("tessdata/eng.traineddata"),
)


def _is_valid_runtime(root: Path, expected_digest: str | None = None) -> bool:
    if not all((root / relative).is_file() for relative in _REQUIRED_RUNTIME_FILES):
        return False
    if expected_digest is None:
        return True
    try:
        return (root / _HASH_MARKER).read_text(encoding="ascii").strip() == expected_digest
    except OSError:
        return False


def _archive_digest(archive_path: Path) -> str:
    digest = hashlib.sha256()
    with archive_path.open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_archive_safely(archive_path: Path, destination: Path) -> None:
    destination_root = destination.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            relative = PurePosixPath(info.filename.replace("\\", "/"))
            if (
                relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or any(":" in part for part in relative.parts)
            ):
                raise OcrUnavailableError("Bundled Tesseract archive contains an unsafe path")
            if info.is_dir():
                continue
            target = destination.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(destination_root):
                raise OcrUnavailableError("Bundled Tesseract archive contains an unsafe path")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _extract_bundled_runtime(archive_path: Path, cache_root: Path | None = None) -> Path:
    try:
        digest = _archive_digest(archive_path)
        cache = cache_root or user_cache_path("DockMask", "Triema", ensure_exists=False)
        runtime_parent = cache / "ocr"
        runtime_root = runtime_parent / digest
        if _is_valid_runtime(runtime_root, digest):
            return runtime_root

        runtime_parent.mkdir(parents=True, exist_ok=True)
        staging = runtime_parent / f".{digest}.{os.getpid()}.{uuid4().hex}.tmp"
        staging.mkdir()
        try:
            _extract_archive_safely(archive_path, staging)
            if not _is_valid_runtime(staging):
                raise OcrUnavailableError("Bundled Tesseract runtime is incomplete")
            (staging / _HASH_MARKER).write_text(digest, encoding="ascii")
            if runtime_root.exists() and not _is_valid_runtime(runtime_root, digest):
                shutil.rmtree(runtime_root)
            try:
                staging.replace(runtime_root)
            except OSError:
                if not _is_valid_runtime(runtime_root, digest):
                    raise
            return runtime_root
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
    except OcrUnavailableError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise OcrUnavailableError("Bundled Tesseract runtime could not be prepared") from exc


def _runtime_root() -> Path | None:
    configured = os.environ.get("DOCKMASK_TESSERACT_DIR")
    if configured:
        candidate = Path(configured)
        if _is_valid_runtime(candidate):
            return candidate.resolve()
    project_root = Path(__file__).resolve().parents[3]
    for candidate in (project_root / "tmp" / "tesseract", project_root / "vendor" / "tesseract"):
        if _is_valid_runtime(candidate):
            return candidate.resolve()
    bundle = getattr(sys, "_MEIPASS", None)
    archive = Path(bundle) / "ocr" / _ARCHIVE_NAME if bundle else None
    if archive and archive.is_file():
        try:
            return _extract_bundled_runtime(archive)
        except OcrUnavailableError as exc:
            logger.warning("Bundled Tesseract runtime is unavailable: %s", exc)
    return None


class TesseractOcrProvider:
    def __init__(self, runtime_root: str | Path | None = None, *, dpi: int = 300) -> None:
        self.runtime_root = Path(runtime_root).resolve() if runtime_root else _runtime_root()
        self.dpi = dpi

    @property
    def available(self) -> bool:
        root = self.runtime_root
        return bool(root and _is_valid_runtime(root))

    def check_runtime(self) -> str:
        if not self.available or self.runtime_root is None:
            raise OcrUnavailableError("Tesseract runtime is unavailable")
        completed = subprocess.run(
            [str(self.runtime_root / "tesseract.exe"), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._environment(),
            startupinfo=self._startupinfo(),
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            raise OcrProcessingError(
                completed.stderr.strip()[:500] or "Tesseract runtime self-test failed"
            )
        return completed.stdout.splitlines()[0] if completed.stdout else "tesseract"

    def _environment(self) -> dict[str, str]:
        assert self.runtime_root is not None
        environment = os.environ.copy()
        environment["TESSDATA_PREFIX"] = str(self.runtime_root / "tessdata")
        environment["PATH"] = str(self.runtime_root) + os.pathsep + environment.get("PATH", "")
        return environment

    @staticmethod
    def _startupinfo() -> subprocess.STARTUPINFO | None:
        if os.name != "nt":
            return None
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startupinfo

    def extract_page(
        self,
        file_path: str | Path,
        page_number: int,
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> list[TextBlock]:
        if not self.available or self.runtime_root is None:
            raise OcrUnavailableError("Tesseract runtime is unavailable")
        if cancel_check:
            cancel_check()
        with fitz.open(file_path) as document:
            page = document[page_number]
            scale = self.dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_width, image_height = pixmap.width, pixmap.height
            page_width, page_height = page.rect.width, page.rect.height
            with tempfile.TemporaryDirectory(prefix="dockmask-ocr-") as temporary:
                image_path = Path(temporary) / "page.png"
                pixmap.save(image_path)
                output = self._run_tesseract(image_path, cancel_check)
        return self._parse_tsv(
            output,
            page_number,
            image_width=image_width,
            image_height=image_height,
            page_width=page_width,
            page_height=page_height,
        )

    def _run_tesseract(
        self,
        image_path: Path,
        cancel_check: Callable[[], None] | None,
    ) -> str:
        assert self.runtime_root is not None
        process = subprocess.Popen(
            [
                str(self.runtime_root / "tesseract.exe"),
                str(image_path),
                "stdout",
                "-l",
                "rus+eng",
                "--oem",
                "1",
                "--psm",
                "6",
                "tsv",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self._environment(),
            startupinfo=self._startupinfo(),
        )
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                try:
                    if cancel_check:
                        cancel_check()
                except BaseException:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise
        if process.returncode != 0:
            raise OcrProcessingError(stderr.strip()[:500] or "Tesseract failed")
        return stdout

    @staticmethod
    def _parse_tsv(
        value: str,
        page_number: int,
        *,
        image_width: int,
        image_height: int,
        page_width: float,
        page_height: float,
    ) -> list[TextBlock]:
        lines: defaultdict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in csv.DictReader(value.splitlines(), delimiter="\t"):
            text = (row.get("text") or "").strip()
            try:
                confidence = float(row.get("conf") or -1)
            except ValueError:
                confidence = -1
            if text and confidence >= 20:
                key = tuple(row.get(name, "") for name in ("page_num", "block_num", "par_num", "line_num"))
                lines[key].append(row)

        scale_x = page_width / max(image_width, 1)
        scale_y = page_height / max(image_height, 1)
        blocks: list[TextBlock] = []
        for index, words in enumerate(lines.values()):
            parts: list[str] = []
            boxes: list[tuple[int, int, float, float, float, float]] = []
            for word in words:
                if parts:
                    parts.append(" ")
                start = sum(len(part) for part in parts)
                text = word["text"].strip()
                parts.append(text)
                end = start + len(text)
                left = float(word["left"]) * scale_x
                top = float(word["top"]) * scale_y
                right = (float(word["left"]) + float(word["width"])) * scale_x
                bottom = (float(word["top"]) + float(word["height"])) * scale_y
                boxes.append((start, end, left, top, right, bottom))
            line_text = "".join(parts)
            if not line_text:
                continue
            bbox = (
                min(item[2] for item in boxes),
                min(item[3] for item in boxes),
                max(item[4] for item in boxes),
                max(item[5] for item in boxes),
            )
            blocks.append(
                TextBlock(
                    block_id=f"pdf_page_{page_number}_ocr_{index}",
                    text=line_text,
                    kind=BlockKind.PDF_OCR_BLOCK,
                    location=Location(page_number=page_number, bbox=bbox, ocr_words=tuple(boxes)),
                )
            )
        return blocks
