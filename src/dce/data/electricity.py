"""Commercial electricity for one ZIP. Reads the bundled seed. No network.

Fallback, first hit wins:

1. ``utility_tariff``. The county's utility has a tariff row (``pge_pdf`` or
   ``openei``). PG&E territory keeps Schedule B-10: energy and a separate
   monthly demand charge.
2. ``utility_average``. That utility's EIA-861 commercial average price.
   ``demand_rate_kw`` is 0. The average is revenue divided by sales, so
   demand charges, customer charges, and riders are already in the $/kWh.
   Adding a demand charge on top would count them twice.
3. ``state``. EIA Electric Power Monthly Table 5.6.A, commercial, for the
   state. Demand is 0 for the same reason.
4. ``national``. The U.S. total on that table. Demand is 0.

The county's utility is the EIA-861 service-territory utility with the
largest commercial megawatthours. A county name that matches two census
counties is left unassigned and the state price is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from dce.data.seed_csv import PublicSeedError, read_seed_csv
from dce.model.types import GeoContext

_TARIFF_SOURCES = frozenset({"pge_pdf", "openei"})
_AVERAGE_SOURCE = "eia861"


@dataclass(frozen=True)
class ElectricityResolution:
    """Energy and demand charges for one ZIP, with the rung that supplied them."""

    zip_code: str
    tier: str
    utility_id: str
    utility_name: str
    schedule: str
    energy_rate_kwh: float
    demand_rate_kw: float
    demand_embedded: bool
    as_of: str
    source: str
    citation: str


@dataclass(frozen=True)
class _Rate:
    level: str
    geo_id: str
    name: str
    energy_rate_kwh: float
    demand_rate_kw: float | None
    schedule: str
    as_of: str
    source: str
    citation: str


@dataclass(frozen=True)
class _Tables:
    by_utility: dict[str, tuple[_Rate, ...]]
    by_state: dict[str, _Rate]
    national: _Rate
    county_utility: dict[str, str]


def resolve_electricity(geo: GeoContext) -> ElectricityResolution:
    """Return the commercial rate for ``geo`` from the bundled seed."""
    tables = _load()
    utility_id = tables.county_utility.get(geo.county_fips, "")
    rows = tables.by_utility.get(utility_id, ())
    tariff = _pick_tariff(rows)
    if tariff is not None:
        return _resolution(geo, "utility_tariff", utility_id, tariff, embedded=False)
    average = _pick_average(rows)
    if average is not None:
        return _resolution(geo, "utility_average", utility_id, average, embedded=True)
    state = tables.by_state.get(geo.state)
    if state is not None:
        return _resolution(geo, "state", "", state, embedded=True)
    return _resolution(geo, "national", "", tables.national, embedded=True)


@lru_cache(maxsize=1)
def _load() -> _Tables:
    by_utility: dict[str, list[_Rate]] = {}
    by_state: dict[str, _Rate] = {}
    national: _Rate | None = None
    for raw in read_seed_csv("electricity_commercial.csv"):
        rate = _parse_rate(raw)
        if rate.level == "utility":
            by_utility.setdefault(rate.geo_id, []).append(rate)
        elif rate.level == "state":
            by_state[rate.geo_id] = rate
        elif rate.level == "national" and rate.geo_id == "US":
            national = rate
    if national is None:
        raise PublicSeedError("Electricity seed has no national commercial price.")
    counties: dict[str, str] = {}
    for raw in read_seed_csv("county_utility.csv"):
        fips = raw["county_fips"].strip()
        utility_id = raw["utility_id"].strip()
        if len(fips) != 5 or not utility_id.isdigit():
            raise PublicSeedError(f"County utility row {fips!r} / {utility_id!r} is not usable.")
        counties[fips] = utility_id
    return _Tables(
        by_utility={key: tuple(value) for key, value in by_utility.items()},
        by_state=by_state,
        national=national,
        county_utility=counties,
    )


def _parse_rate(raw: dict[str, str]) -> _Rate:
    demand_text = raw.get("demand_rate_kw", "").strip()
    try:
        energy = float(raw["energy_rate_kwh"])
        demand = None if demand_text == "" else float(demand_text)
    except (KeyError, ValueError) as exc:
        raise PublicSeedError(f"Electricity row {raw.get('geo_id')!r} is not usable.") from exc
    if energy < 0.0 or (demand is not None and demand < 0.0):
        raise PublicSeedError(f"Electricity row {raw.get('geo_id')!r} has a negative rate.")
    return _Rate(
        level=raw.get("level", "").strip(),
        geo_id=raw.get("geo_id", "").strip(),
        name=raw.get("name", "").strip(),
        energy_rate_kwh=energy,
        demand_rate_kw=demand,
        schedule=raw.get("schedule", "").strip(),
        as_of=raw.get("as_of", "").strip(),
        source=raw.get("source", "").strip(),
        citation=raw.get("citation", "").strip(),
    )


def _pick_tariff(rows: tuple[_Rate, ...]) -> _Rate | None:
    tariffs = [row for row in rows if row.source in _TARIFF_SOURCES]
    if not tariffs:
        return None
    tariffs.sort(key=lambda row: (row.demand_rate_kw is None, row.schedule, row.source))
    return tariffs[0]


def _pick_average(rows: tuple[_Rate, ...]) -> _Rate | None:
    averages = [row for row in rows if row.source == _AVERAGE_SOURCE]
    if not averages:
        return None
    averages.sort(key=lambda row: row.schedule)
    return averages[0]


def _resolution(
    geo: GeoContext,
    tier: str,
    utility_id: str,
    rate: _Rate,
    *,
    embedded: bool,
) -> ElectricityResolution:
    demand = 0.0 if embedded or rate.demand_rate_kw is None else rate.demand_rate_kw
    # A tariff row with no demand number is still a tariff, and demand is embedded.
    if rate.demand_rate_kw is None:
        embedded = True
        demand = 0.0
    return ElectricityResolution(
        zip_code=geo.zip_code,
        tier=tier,
        utility_id=utility_id,
        utility_name=rate.name,
        schedule=rate.schedule,
        energy_rate_kwh=rate.energy_rate_kwh,
        demand_rate_kw=demand,
        demand_embedded=embedded,
        as_of=rate.as_of,
        source=rate.source,
        citation=rate.citation,
    )
