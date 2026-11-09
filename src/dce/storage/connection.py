"""SQLite connection helper.

Contract
--------
``get_connection(user_data_dir) -> sqlite3.Connection``

Create ``dce.sqlite`` under the directory from :mod:`dce.config` when it
is missing, enable foreign keys, and apply migrations. A second call on
the same directory leaves existing rows in place. Copying the bundled
seed into that database is a later milestone.

Do not download anything. Do not read API keys.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dce.config import DB_FILENAME
from dce.storage.migrate import migrate


def get_connection(user_data_dir: Path) -> sqlite3.Connection:
    """Open the user database, creating it and applying migrations."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(user_data_dir / DB_FILENAME)
    conn.execute("PRAGMA foreign_keys = ON")
    migrate(conn)
    return conn


def enable_wal(conn: sqlite3.Connection) -> None:
    """Let a precompute writer and its worker readers share one database."""
    conn.execute("PRAGMA journal_mode=WAL")
