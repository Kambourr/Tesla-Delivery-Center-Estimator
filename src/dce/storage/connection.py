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

# Compressed ZIP documents are a few kilobytes. A 512-byte page keeps the
# unused tail of each overflow chain small. 4096-byte pages would add about
# 2 KiB of waste per ZIP and push the nationwide file over the bundle budget.
RESULTS_PAGE_SIZE = 512


def get_connection(user_data_dir: Path) -> sqlite3.Connection:
    """Open the user database, creating it and applying migrations."""
    user_data_dir.mkdir(parents=True, exist_ok=True)
    path = user_data_dir / DB_FILENAME
    new_file = not path.is_file()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    if new_file:
        conn.execute(f"PRAGMA page_size = {RESULTS_PAGE_SIZE}")
    migrate(conn)
    return conn


def finish_results_database(conn: sqlite3.Connection) -> None:
    """Checkpoint, set the page size, and VACUUM so the file holds no free pages.

    ``page_size`` on a database that already has tables takes effect at VACUUM.
    """
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute(f"PRAGMA page_size = {RESULTS_PAGE_SIZE}")
    conn.execute("VACUUM")
    conn.commit()


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open an existing database without creating a journal or migrating.

    ``immutable=1`` keeps SQLite from writing a sidecar next to a file that
    lives inside a packaged app. The caller does not need a writable directory.
    """
    if not db_path.is_file():
        raise FileNotFoundError(f"Results database is missing: {db_path}")
    uri = f"{db_path.resolve().as_uri()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn


def can_open_readonly(db_path: Path) -> bool:
    """Return whether ``db_path`` can be queried without writing beside it."""
    try:
        conn = open_readonly(db_path)
    except (OSError, sqlite3.Error):
        return False
    try:
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    except sqlite3.Error:
        return False
    finally:
        conn.close()
    return True


def enable_wal(conn: sqlite3.Connection) -> None:
    """Let a precompute writer and its worker readers share one database."""
    conn.execute("PRAGMA journal_mode=WAL")
