"""Application settings and local data paths."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        extra="ignore",
    )

    env: str = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    data_dir: Path = Field(
        default_factory=lambda: user_data_path("DockMask", "Triema", ensure_exists=False)
    )

    @field_validator("host")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("APP_HOST must be a loopback address")
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "dockmask.sqlite3"

    @property
    def files_path(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def logs_path(self) -> Path:
        return self.data_dir / "logs"
