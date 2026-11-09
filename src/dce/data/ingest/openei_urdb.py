"""OpenEI Utility Rate Database fetch.

Contract
--------
Allowlisted host: ``api.openei.org``. Structured fallback when a hand-parsed
utility schedule is missing. ``source`` on the result is ``openei``.

An OpenEI key is intentionally absent from ``.env.example`` until this
loader is implemented. No SQLite in this module. The cost model never
imports this module; the orchestrator stores the result and reads it back
through the repository.

Milestone M0: stub. No network calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UrdbRate:
    """Energy and demand charges from one URDB rate."""

    utility_id: str
    schedule: str
    geography: str
    energy_rate_kwh: float | None
    demand_rate_kw: float | None
    as_of: str
    source: str


def fetch_urdb_rate(utility_id: str, schedule: str) -> UrdbRate:
    """Download one URDB schedule. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.openei_urdb.fetch_urdb_rate is a stub (M0)")
