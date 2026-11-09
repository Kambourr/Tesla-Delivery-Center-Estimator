"""EIA retail electricity price fetch.

Contract
--------
Allowlisted host: ``eia.gov``. Commercial retail ``$/kWh`` by state from
Electric Power Monthly Table 5.6.A. ``source`` on the result is ``eia``.

``estimate`` does not call this module. It reads ``data/seed/electricity_commercial.csv``.
A curator runs this fetch, then ``scripts/build_local_cost_seeds.py``.

No SQLite in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from dce.data.ingest.http import IngestError, request_bytes
from dce.data.ingest.xlsx_table import read_xlsx_rows

EPM_XLSX_URL = "https://www.eia.gov/electricity/monthly/xls/table_5_06_a.xlsx"
_COMMERCIAL_COLUMN = 3

# EIA prints these names. Census divisions are not states and are skipped.
_STATE_NAMES = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


@dataclass(frozen=True)
class RetailRate:
    """One commercial retail electricity price. Demand is already inside the average."""

    geography: str
    energy_rate_kwh: float | None
    as_of: str
    source: str


def commercial_prices_per_kwh(rows: list[list[str]]) -> dict[str, float]:
    """Return postal code (and ``US``) to commercial ``$/kWh`` from Table 5.6.A rows.

    Column 3 is the latest commercial month. The workbook stores cents.
    A blank or non-numeric cell is skipped.
    """
    found: dict[str, float] = {}
    for row in rows:
        if not row:
            continue
        label = row[0].replace("\n", " ").strip()
        if len(row) <= _COMMERCIAL_COLUMN:
            continue
        try:
            cents = float(row[_COMMERCIAL_COLUMN])
        except ValueError:
            continue
        if label == "U.S. Total":
            found["US"] = cents / 100.0
        postal = _STATE_NAMES.get(label)
        if postal is not None:
            found[postal] = cents / 100.0
    return found


def fetch_state_commercial_rate(state: str) -> RetailRate:
    """Download Table 5.6.A and return the commercial average for ``state``."""
    code = state.strip().upper()
    if len(code) != 2 or code not in set(_STATE_NAMES.values()):
        raise IngestError(f"EIA state must be a US postal code, got {state!r}.")
    payload = request_bytes(EPM_XLSX_URL, max_bytes=2_000_000)
    prices = commercial_prices_per_kwh(read_xlsx_rows(payload))
    if code not in prices:
        raise IngestError(f"EIA Table 5.6.A has no commercial price for {code}.")
    return RetailRate(
        geography=code,
        energy_rate_kwh=prices[code],
        as_of="",
        source="eia",
    )
