"""Lifecycle-owned SQLite connection and schema initialization."""

from __future__ import annotations

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    document_format TEXT NOT NULL,
    entity_types TEXT NOT NULL,
    input_path TEXT NOT NULL,
    output_path TEXT,
    json_report_path TEXT,
    xlsx_report_path TEXT,
    progress INTEGER NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 100),
    questions TEXT NOT NULL DEFAULT '[]',
    answers TEXT NOT NULL DEFAULT '{}',
    pending_matches TEXT NOT NULL DEFAULT '[]',
    total_replacements INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    base_url TEXT,
    scope TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_config (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    base_url TEXT,
    scope TEXT,
    updated_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.connection: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.executescript(SCHEMA)
        columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(jobs)")).fetchall()
        }
        if "pending_matches" not in columns:
            await connection.execute(
                "ALTER TABLE jobs ADD COLUMN pending_matches TEXT NOT NULL DEFAULT '[]'"
            )
        if "scope" not in columns:
            await connection.execute("ALTER TABLE jobs ADD COLUMN scope TEXT")
        if "label_style" not in columns:
            await connection.execute(
                "ALTER TABLE jobs ADD COLUMN label_style TEXT NOT NULL DEFAULT 'full'"
            )
        config_columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(app_config)")).fetchall()
        }
        if "scope" not in config_columns:
            await connection.execute("ALTER TABLE app_config ADD COLUMN scope TEXT")
        await connection.commit()
        self.connection = connection
        return connection

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def require_connection(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("database is not connected")
        return self.connection
