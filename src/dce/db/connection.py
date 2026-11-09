"""SQLite connection helper.

Contract
--------
``get_connection(user_data_dir) -> sqlite3.Connection``

Open (and, in a later milestone, create) ``dce.sqlite`` under the user data
directory from :mod:`dce.config`. Enable foreign keys. On first launch, copy
bundled seed tables so the app answers a ZIP with no network.

Do not download anything. Do not read API keys.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(user_data_dir: Path) -> sqlite3.Connection:
    """Open the user database. Not implemented in M0."""
    raise NotImplementedError("dce.db.connection.get_connection is a stub (M0)")
