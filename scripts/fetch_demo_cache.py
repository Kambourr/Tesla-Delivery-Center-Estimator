"""Load the San Mateo public-data demo into SQLite.

Default mode reads ``data/demo/san_mateo`` and does not need API keys or the
network. ``--refresh`` calls the allowlisted Census, BLS, and data.ca.gov
loaders. Census refresh needs ``CENSUS_API_KEY``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dce.data.demo_seed import (
    DemoSeedError,
    database_directory,
    load_san_mateo_demo,
    refresh_san_mateo,
)
from dce.data.ingest.http import IngestError
from dce.data.persist import PersistError
from dce.storage.connection import get_connection


def main(argv: list[str] | None = None) -> int:
    """Load fixtures, or refresh them when ``--refresh`` is set."""
    parser = argparse.ArgumentParser(
        description=(
            "Load San Mateo ACS, OEWS, and DMV vehicle counts into dce.sqlite. "
            "The default uses committed fixtures and does not need API keys."
        )
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="dce.sqlite file or its parent directory. Default is the OS user data directory.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch from allowlisted hosts instead of fixtures. Census needs CENSUS_API_KEY.",
    )
    args = parser.parse_args(argv)
    try:
        conn = get_connection(database_directory(args.db))
        try:
            counts = refresh_san_mateo(conn) if args.refresh else load_san_mateo_demo(conn)
        finally:
            conn.close()
    except (DemoSeedError, IngestError, PersistError, OSError) as exc:
        print(f"dce: {exc}", file=sys.stderr)
        return 1
    print(
        "Loaded San Mateo demo: "
        f"{counts.acs_rows} ACS rows, {counts.oews_rows} OEWS rows, {counts.ev_rows} EV rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
