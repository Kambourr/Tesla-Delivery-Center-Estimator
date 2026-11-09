"""BLS OEWS wage fetch.

Contract
--------
Allowlisted host: ``bls.gov``. Primary occupation is SOC ``49-3023``
(Automotive Service Technicians and Mechanics). Map ZIP to metro with the
HUD crosswalk (see :mod:`dce.data.ingest.hud_crosswalk`).

Refresh annually (May OEWS). Stale after 18 months. ``BLS_API_KEY`` is
optional. This function does not open SQLite. Milestone M0 does not call BLS.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OewsWage:
    """Metro occupation wage. Annual dollars."""

    area_code: str
    area_name: str
    soc: str
    soc_title: str
    mean_annual: float | None
    median_annual: float | None
    as_of: str


def fetch_oews_wage(area_code: str, soc: str) -> OewsWage:
    """Download one metro × SOC wage. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.bls_oews.fetch_oews_wage is a stub (M0)")
