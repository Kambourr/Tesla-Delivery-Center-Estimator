"""Apply ``schema.sql`` idempotently.

Contract
--------
``migrate(conn) -> None`` runs the packaged schema against an open
connection. Repeating the call on a database that is already current must
succeed and leave rows in place. No network.

Milestone M0: raises ``NotImplementedError``. ``schema.sql`` is comments only.
"""

from __future__ import annotations

import sqlite3


def migrate(conn: sqlite3.Connection) -> None:
    """Apply the packaged schema. Not implemented in M0."""
    raise NotImplementedError("dce.db.migrate.migrate is a stub (M0)")
