"""California ZEV / fuel-type counts by ZIP.

Contract
--------
Allowlisted hosts: ``energy.ca.gov`` and ``data.ca.gov``. ``source`` is
``cec``, ``dmv``, or ``fallback``.

Outside California, a later milestone flags
``ev_proxy=acs_national_fallback``. Refresh about annually. Stale after 18
months. No API key for the file downloads. No SQLite in this module.

Milestone M0: stub. No network calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvZipCount:
    """Light-duty vehicle counts for one ZIP."""

    zip_code: str
    state: str
    bev: float | None
    phev: float | None
    fcev: float | None
    total_ldv: float | None
    as_of: str
    source: str


def fetch_ev_zip(zip_code: str) -> EvZipCount:
    """Download ZEV counts for one ZIP. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.ca_ev.fetch_ev_zip is a stub (M0)")
