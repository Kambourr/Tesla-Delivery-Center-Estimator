"""Print fresh / aging / stale / missing for each ``source_registry`` row.

Reads an existing database and does not create one, refresh sources, or use
the network. ``--today`` pins the calendar date so a report is repeatable.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from dce.config import user_db_path
from dce.data.registry import parse_as_of, staleness_status
from dce.storage.repository import list_sources


def main(argv: list[str] | None = None) -> int:
    """Print one status line per stored source."""
    parser = argparse.ArgumentParser(
        description="Report source_registry staleness. Does not refresh data and does not create a database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Path to dce.sqlite. Default is the OS user database.",
    )
    parser.add_argument(
        "--today",
        help="ISO date used as today. Default is the local date.",
    )
    args = parser.parse_args(argv)
    path = user_db_path() if args.db is None else args.db
    if not path.is_file():
        print(f"No database at {path}.")
        return 0
    try:
        today = date.today() if args.today is None else date.fromisoformat(args.today)
    except ValueError:
        print(f"dce: --today must be an ISO date, got {args.today!r}.", file=sys.stderr)
        return 1
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        print(f"dce: could not open {path}: {exc}", file=sys.stderr)
        return 1
    try:
        try:
            records = list_sources(conn)
        except sqlite3.Error as exc:
            print(f"dce: {path} has no readable source_registry ({exc}).", file=sys.stderr)
            return 1
    finally:
        conn.close()
    if not records:
        print("source_registry is empty.")
        return 0
    for record in records:
        try:
            status = staleness_status(parse_as_of(record.as_of), record.ttl_days, today)
        except ValueError as exc:
            print(f"dce: {record.source_id}: {exc}", file=sys.stderr)
            return 1
        shown = "" if record.as_of is None else record.as_of
        print(f"{record.source_id}\t{shown}\t{status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
