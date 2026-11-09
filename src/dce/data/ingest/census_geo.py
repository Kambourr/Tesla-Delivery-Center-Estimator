"""Census TIGER geometry fetch.

Contract
--------
Allowlisted host: ``census.gov``. Return a local path the caller will store
under the user data directory. Do not commit the national ZCTA extract.
The San Mateo demo may later ship a small GeoPackage in ``data/demo/``.

No API key. This module does not open SQLite. Milestone M0 does not download.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeometryFetch:
    """One simplified geometry extract. ``path`` is where the bytes were written."""

    geoid: str
    path: Path


def fetch_county_block_groups(state_fips: str, county_fips: str) -> GeometryFetch:
    """Download and simplify one county's block groups. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.census_geo.fetch_county_block_groups is a stub (M0)")
