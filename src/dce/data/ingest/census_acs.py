"""Census ACS 5-year fetch (ZCTA and, later, catchment block groups).

Contract
--------
Allowlisted host: ``api.census.gov``. Variables include population
(``B01003_001E``), median household income (``B19013_001E``), vehicles
available, commute, and median home value (``B25077``) for the rent model.
Refresh annually. Stale if ``as_of`` is older than 18 months.

``fetch_zcta_acs`` may use ``CENSUS_API_KEY``. It returns a
:class:`ZctaAcs` and does not open SQLite. The orchestrator persists rows
through :mod:`dce.storage.repository`. No calls at import time.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ZctaAcs:
    """ACS facts for one ZCTA. Counts and dollars are ``None`` when suppressed."""

    zcta: str
    year: int
    population: float | None
    median_hh_income: float | None
    vehicles_available: float | None
    mean_commute: float | None
    median_home_value: float | None


def fetch_zcta_acs(zcta: str, *, year: int) -> ZctaAcs:
    """Download ACS 5-year fields for one ZCTA. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.census_acs.fetch_zcta_acs is a stub (M0)")
