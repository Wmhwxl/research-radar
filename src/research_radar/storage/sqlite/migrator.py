from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path


def connect_sqlite(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def apply_migrations(path: str | Path) -> list[str]:
    conn = connect_sqlite(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        applied = {
            row["version"]
            for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        }
        package = resources.files("src.research_radar.storage.sqlite.migrations")
        migration_files = sorted(item for item in package.iterdir() if item.name.endswith(".sql"))
        new_versions: list[str] = []
        for item in migration_files:
            version = item.name.split("_", 1)[0]
            if version in applied:
                continue
            sql = item.read_text(encoding="utf-8")
            with conn:
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            new_versions.append(version)
        return new_versions
    finally:
        conn.close()
