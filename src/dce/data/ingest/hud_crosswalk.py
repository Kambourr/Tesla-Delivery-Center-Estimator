"""HUD–USPS ZIP crosswalk fetch.

Contract
--------
Allowlisted host: ``huduser.gov``. ZIP to county and CBSA. Token:
``HUD_TOKEN`` from the environment, never from git.

A bundled crosswalk must let rent resolution work offline; that bundle is
seed data, not this fetch. Refresh quarterly. Stale after 2 quarters.
Does not open SQLite. :func:`dce.geo.resolve.resolve_zip` reads the cache.

Milestone M0: stub. No network calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZipCrosswalk:
    """One ZIP row from the HUD crosswalk. Codes are text."""

    zip_code: str
    county_fips: str
    cbsa: str
    state: str


def fetch_zip_crosswalk(zip_code: str) -> tuple[ZipCrosswalk, ...]:
    """Download HUD rows for one ZIP. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.hud_crosswalk.fetch_zip_crosswalk is a stub (M0)")
