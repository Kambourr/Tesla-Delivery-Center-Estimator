"""Apply ``schema.sql`` idempotently.

Contract
--------
``migrate(conn) -> None`` runs the packaged schema against an open
connection. Repeating the call on a database that is already current
succeeds and leaves rows in place. No network.

Milestone M1 applies ``schema.sql`` (version 1). Later milestones that
change columns add a new ``schema_migrations`` version instead of editing
the version-1 statements in place.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _read_schema_sql() -> str:
    if not _SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"Packaged schema is missing: {_SCHEMA_PATH}")
    return _SCHEMA_PATH.read_text(encoding="utf-8")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the packaged schema. Safe to repeat."""
    conn.executescript(_read_schema_sql())
