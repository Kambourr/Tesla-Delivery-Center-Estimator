"""Refresh San Mateo ACS, OEWS, and DMV rows from allowlisted hosts.

Census needs ``CENSUS_API_KEY``. BLS and the California DMV file do not.
This script does not scrape listing sites and does not run on import.
``scripts/fetch_demo_cache.py`` without ``--refresh`` is the no-key path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dce.data.demo_seed import DemoSeedError, database_directory, refresh_san_mateo
from dce.data.ingest.http import IngestError
from dce.data.persist import PersistError
from dce.storage.connection import get_connection


def main(argv: list[str] | None = None) -> int:
    """Fetch the three M2 sources and upsert them."""
    parser = argparse.ArgumentParser(
        description=(
            "Refresh San Mateo ACS, OEWS, and DMV vehicle counts from allowlisted hosts. "
            "Census needs CENSUS_API_KEY."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="dce.sqlite file or its parent directory. Default is the OS user data directory.",
    )
    args = parser.parse_args(argv)
    try:
        conn = get_connection(database_directory(args.db))
        try:
            counts = refresh_san_mateo(conn)
        finally:
            conn.close()
    except (DemoSeedError, IngestError, PersistError, OSError) as exc:
        print(f"dce: {exc}", file=sys.stderr)
        return 1
    print(
        "Refreshed San Mateo sources: "
        f"{counts.acs_rows} ACS rows, {counts.oews_rows} OEWS rows, {counts.ev_rows} EV rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
