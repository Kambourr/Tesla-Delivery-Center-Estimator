"""EIA retail electricity price fetch.

Contract
--------
Allowlisted host: ``eia.gov``. Commercial retail ``$/kWh`` by state.
Key: ``EIA_API_KEY``. ``source`` on the result is ``eia``.

Refresh monthly. Stale after 6 months. No SQLite in this module.
Milestone M0: stub. No network calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetailRate:
    """One commercial retail electricity price."""

    geography: str
    energy_rate_kwh: float | None
    as_of: str
    source: str


def fetch_state_commercial_rate(state: str) -> RetailRate:
    """Download the state commercial retail rate. Not implemented in M0."""
    raise NotImplementedError(
        "dce.data.ingest.eia_rates.fetch_state_commercial_rate is a stub (M0)"
    )
