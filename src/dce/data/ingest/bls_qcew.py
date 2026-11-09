"""BLS QCEW county industry-wage fetch.

Contract
--------
Allowlisted host: ``bls.gov``. QCEW is NAICS, not SOC. Use auto-dealer and
repair industries as a county scaler against the OEWS metro occupation wage.
Do not treat QCEW as a substitute for SOC ``49-3023``.

Refresh quarterly. Stale after 4 quarters. No SQLite in this module.
Milestone M0: stub. No network calls.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QcewCountyWage:
    """County × NAICS average annual pay, used only as a scaler."""

    county_fips: str
    naics: str
    avg_annual_pay: float | None
    as_of: str


def fetch_qcew_wage(county_fips: str, naics: str) -> QcewCountyWage:
    """Download one county industry wage. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.bls_qcew.fetch_qcew_wage is a stub (M0)")
