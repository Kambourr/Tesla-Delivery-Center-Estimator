"""OpenEI Utility Rate Database fetch.

Contract
--------
Allowlisted host: ``api.openei.org``. A tariff row for one utility schedule.
``source`` on the result is ``openei``. The key is ``OPENEI_API_KEY``.

``estimate`` does not call this module. A tariff row in the electricity seed
replaces that utility's EIA-861 average. It is not added on top of the
average: the average already includes demand charges.

No SQLite in this module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dce.data.ingest.http import IngestError, encode_query, request_json

_URDB_URL = "https://api.openei.org/utility_rates"


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


def parse_urdb_item(item: dict[str, object], utility_id: str) -> UrdbRate:
    """Return one URDB item. Energy is the mean of the rate cells. Demand is the max."""
    label = _text(item.get("label")) or _text(item.get("name")) or utility_id
    energy_values = _rate_cells(item.get("energyratestructure"))
    demand_values = _rate_cells(item.get("demandratestructure"))
    return UrdbRate(
        utility_id=utility_id,
        schedule=label,
        geography=_text(item.get("utility")),
        energy_rate_kwh=(sum(energy_values) / len(energy_values)) if energy_values else None,
        demand_rate_kw=max(demand_values) if demand_values else None,
        as_of=_text(item.get("startdate")),
        source="openei",
    )


def fetch_urdb_rate(utility_id: str, schedule: str) -> UrdbRate:
    """Download one approved URDB schedule for an EIA utility id.

    ``schedule`` matches the rate ``label`` or ``name``, ignoring case.
    """
    code = utility_id.strip()
    name = schedule.strip()
    if not code.isdigit():
        raise IngestError(f"OpenEI utility id must be digits, got {utility_id!r}.")
    if name == "":
        raise IngestError("OpenEI schedule must not be empty.")
    key = os.environ.get("OPENEI_API_KEY", "").strip()
    if key == "":
        raise IngestError("OPENEI_API_KEY is not set.")
    query = encode_query(
        {
            "version": "7",
            "format": "json",
            "detail": "full",
            "approved": "true",
            "eia": code,
            "api_key": key,
        }
    )
    payload = request_json(f"{_URDB_URL}?{query}")
    if not isinstance(payload, dict):
        raise IngestError("OpenEI did not return a JSON object.")
    items = payload.get("items")
    if not isinstance(items, list):
        raise IngestError("OpenEI response has no items list.")
    wanted = name.casefold()
    for raw in items:
        if not isinstance(raw, dict):
            continue
        label = _text(raw.get("label")) or _text(raw.get("name"))
        if label.casefold() == wanted:
            return parse_urdb_item(raw, code)
    raise IngestError(f"OpenEI has no approved rate {name!r} for utility {code}.")


def _rate_cells(structure: object) -> list[float]:
    if not isinstance(structure, list):
        return []
    found: list[float] = []
    for period in structure:
        if not isinstance(period, list):
            continue
        for tier in period:
            if not isinstance(tier, dict):
                continue
            rate = tier.get("rate")
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                continue
            found.append(float(rate))
    return found


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
