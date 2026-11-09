"""Commercial property-tax rate for one ZIP. Reads the bundled seed. No network.

The rate is the effective tax on a $1 million commercial building plus
$200,000 of fixtures, from the Lincoln Institute / Minnesota Center for
Fiscal Excellence 50-State Property Tax Comparison Study (taxes paid in
2024). It is a fraction of market value (0.01808 is 1.808%).

Fallback, first hit wins:

1. ``county``. The ZIP's county is one of the studied cities or the studied
   rural municipality.
2. ``state_rural``. The county is outside every metro and micro area
   (``cbsa`` is empty). The rung is that state's rural municipality.
3. ``state_urban``. Any other county in the state. The rung is the largest
   city, except Illinois (Aurora, not Chicago) and New York (Buffalo, not
   New York City). Chicago and New York City are county rows.
4. ``national``. The study's 53-city average, 1.755%.

The study does not publish every county. A county that is not in the
appendix uses the state rung. That is a proxy, and the place name on the
result says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from dce.data.seed_csv import PublicSeedError, read_seed_csv
from dce.model.types import GeoContext


@dataclass(frozen=True)
class PropertyTaxResolution:
    """Effective commercial property-tax rate for one ZIP."""

    zip_code: str
    tier: str
    state: str
    county_fips: str
    place: str
    effective_rate: float
    as_of: str
    citation: str


@dataclass(frozen=True)
class _Row:
    level: str
    state: str
    county_fips: str
    place: str
    effective_rate: float
    as_of: str
    citation: str


@dataclass(frozen=True)
class _Tables:
    by_county: dict[str, _Row]
    urban: dict[str, _Row]
    rural: dict[str, _Row]
    national: _Row


def resolve_property_tax(geo: GeoContext) -> PropertyTaxResolution:
    """Return the commercial effective rate for ``geo``."""
    tables = _load()
    county = tables.by_county.get(geo.county_fips)
    if county is not None:
        return _resolution(geo, "county", county)
    if geo.cbsa == "":
        rural = tables.rural.get(geo.state)
        if rural is not None:
            return _resolution(geo, "state_rural", rural)
    urban = tables.urban.get(geo.state)
    if urban is not None:
        return _resolution(geo, "state_urban", urban)
    return _resolution(geo, "national", tables.national)


@lru_cache(maxsize=1)
def _load() -> _Tables:
    by_county: dict[str, _Row] = {}
    urban: dict[str, _Row] = {}
    rural: dict[str, _Row] = {}
    national: _Row | None = None
    for raw in read_seed_csv("property_tax_commercial.csv"):
        row = _parse(raw)
        if row.level == "county":
            by_county[row.county_fips] = row
        elif row.level == "state_urban":
            urban[row.state] = row
        elif row.level == "state_rural":
            rural[row.state] = row
        elif row.level == "national":
            national = row
    if national is None:
        raise PublicSeedError("Property-tax seed has no national rate.")
    return _Tables(by_county=by_county, urban=urban, rural=rural, national=national)


def _parse(raw: dict[str, str]) -> _Row:
    try:
        rate = float(raw["effective_rate"])
    except (KeyError, ValueError) as exc:
        raise PublicSeedError(f"Property-tax row {raw.get('place')!r} is not usable.") from exc
    if rate < 0.0:
        raise PublicSeedError(f"Property-tax row {raw.get('place')!r} is negative.")
    return _Row(
        level=raw.get("level", "").strip(),
        state=raw.get("state", "").strip(),
        county_fips=raw.get("county_fips", "").strip(),
        place=raw.get("place", "").strip(),
        effective_rate=rate,
        as_of=raw.get("as_of", "").strip(),
        citation=raw.get("citation", "").strip(),
    )


def _resolution(geo: GeoContext, tier: str, row: _Row) -> PropertyTaxResolution:
    return PropertyTaxResolution(
        zip_code=geo.zip_code,
        tier=tier,
        state=row.state or geo.state,
        county_fips=row.county_fips or geo.county_fips,
        place=row.place,
        effective_rate=row.effective_rate,
        as_of=row.as_of,
        citation=row.citation,
    )
