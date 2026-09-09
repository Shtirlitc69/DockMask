"""Job-scoped local file storage."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import UploadFile


class FileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def job_dir(self, job_id: str) -> Path:
        if not job_id or any(character not in "0123456789abcdef-" for character in job_id.lower()):
            raise ValueError("invalid job id")
        target = (self.root / job_id).resolve()
        if self.root not in target.parents:
            raise ValueError("invalid job path")
        target.mkdir(parents=True, exist_ok=True)
        return target

    async def save_upload(self, job_id: str, upload: UploadFile, suffix: str) -> Path:
        target = self.job_dir(job_id) / f"source.{suffix}"
        await upload.seek(0)
        with target.open("wb") as stream:
            while chunk := await upload.read(1024 * 1024):
                await asyncio.to_thread(stream.write, chunk)
        await upload.seek(0)
        return target
