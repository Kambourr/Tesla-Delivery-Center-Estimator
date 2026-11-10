"""Commercial property-tax rate for one ZIP. Reads the bundled seed. No network.

Source: Lincoln Institute / Minnesota Center for Fiscal Excellence,
50-State Property Tax Comparison Study, taxes paid in 2024 (July 2025).
The class is **commercial**: Appendix Tables 3a (largest city in each
state), 3b (50 largest cities), and 3c (rural municipalities), the $1
million land-and-building parcel with $200,000 of fixtures. It is not the
homestead (residential) class of Tables 2a-2h. New York City, for example,
is 1.418% commercial against 1.249% homestead (Table 2a) or 0.477% with
assessment limits (Table 2b).

``effective_rate`` is the tax on land and building per dollar of land and
building, because the landlord's tax that NNN rent passes through falls on
the building. The published rate divides the whole bill by $1.2 million.
Where fixtures are exempt (Table 4g: New York, Illinois, Massachusetts,
New Jersey, Pennsylvania, Ohio, and others) the whole bill is on the $1
million of real property, so the rate on real property is the bill over $1
million (New York City: $17,014, 1.701%). Elsewhere the published rate is
kept. ``commercial_rate`` keeps the published figure.

``industrial_rate`` is the study's industrial figure (Tables 4a, 4c, 4e:
a manufacturing parcel with $1 million of real property and $1 million of
machinery, inventory, and fixtures, divided by $2 million). It is carried
for provenance and is not applied: a delivery center's landlord pays on the
building, and that table's denominator is half personal property.

Fallback, first hit wins:

1. ``county``. The ZIP's county is one of the studied places.
2. ``cbsa``. The county is in the same CBSA or metropolitan division (then
   the parent CBSA) as a studied large city in the same state. Several
   matches are averaged. New York City and Chicago never stand in for a
   neighbour, because the study says their systems differ from the rest of
   the state, and rural municipalities never stand in for a metro.
   San Mateo County uses San Francisco this way.
3. ``state_rural``. The county is outside every metro and micro area
   (``cbsa`` is empty). The rung is that state's rural municipality.
4. ``state_urban``. Any other county in the state. The rung is the largest
   city, except Illinois (Aurora, not Chicago) and New York (Buffalo, not
   New York City).
5. ``national``. The mean of the 53 Table 3a cities on the same
   real-property basis.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from dce.data.ingest.bls_oews import OewsError, oews_area_for_cbsa
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
    commercial_rate: float
    industrial_rate: float | None
    fixtures_exempt: bool
    source_table: str
    cbsa: str = ""


@dataclass(frozen=True)
class _Row:
    level: str
    state: str
    county_fips: str
    cbsa: str
    place: str
    effective_rate: float
    commercial_rate: float
    industrial_rate: float | None
    fixtures_exempt: bool
    metro_proxy: bool
    source_table: str
    as_of: str
    citation: str


@dataclass(frozen=True)
class _Tables:
    by_county: dict[str, _Row]
    by_cbsa: dict[str, tuple[_Row, ...]]
    urban: dict[str, _Row]
    rural: dict[str, _Row]
    national: _Row


def resolve_property_tax(geo: GeoContext) -> PropertyTaxResolution:
    """Return the commercial effective rate for ``geo``."""
    tables = _load()
    county = tables.by_county.get(geo.county_fips)
    if county is not None:
        return _resolution(geo, "county", county)
    for code in _cbsa_codes(geo.cbsa):
        rows = tuple(row for row in tables.by_cbsa.get(code, ()) if row.state == geo.state)
        if rows:
            return _metro(geo, code, rows)
    if geo.cbsa == "":
        rural = tables.rural.get(geo.state)
        if rural is not None:
            return _resolution(geo, "state_rural", rural)
    urban = tables.urban.get(geo.state)
    if urban is not None:
        return _resolution(geo, "state_urban", urban)
    return _resolution(geo, "national", tables.national)


def _cbsa_codes(cbsa: str) -> tuple[str, ...]:
    if len(cbsa) != 5 or not cbsa.isdigit():
        return ()
    try:
        parent = oews_area_for_cbsa(cbsa)
    except OewsError:
        parent = cbsa
    return (cbsa,) if parent == cbsa else (cbsa, parent)


@lru_cache(maxsize=1)
def _load() -> _Tables:
    by_county: dict[str, _Row] = {}
    by_cbsa: dict[str, list[_Row]] = {}
    urban: dict[str, _Row] = {}
    rural: dict[str, _Row] = {}
    national: _Row | None = None
    for raw in read_seed_csv("property_tax_commercial.csv"):
        row = _parse(raw)
        if row.level == "county":
            by_county[row.county_fips] = row
            if row.metro_proxy and row.cbsa:
                for code in _cbsa_codes(row.cbsa):
                    by_cbsa.setdefault(code, []).append(row)
        elif row.level == "state_urban":
            urban[row.state] = row
        elif row.level == "state_rural":
            rural[row.state] = row
        elif row.level == "national":
            national = row
    if national is None:
        raise PublicSeedError("Property-tax seed has no national rate.")
    return _Tables(
        by_county=by_county,
        by_cbsa={
            code: tuple(sorted(rows, key=lambda r: r.county_fips)) for code, rows in by_cbsa.items()
        },
        urban=urban,
        rural=rural,
        national=national,
    )


def _parse(raw: dict[str, str]) -> _Row:
    place = raw.get("place")
    try:
        rate = float(raw["effective_rate"])
        commercial = float(raw.get("commercial_rate") or raw["effective_rate"])
        industrial_text = (raw.get("industrial_rate") or "").strip()
        industrial = float(industrial_text) if industrial_text else None
    except (KeyError, ValueError) as exc:
        raise PublicSeedError(f"Property-tax row {place!r} is not usable.") from exc
    if rate < 0.0 or commercial < 0.0 or (industrial is not None and industrial < 0.0):
        raise PublicSeedError(f"Property-tax row {place!r} is negative.")
    return _Row(
        level=raw.get("level", "").strip(),
        state=raw.get("state", "").strip(),
        county_fips=raw.get("county_fips", "").strip(),
        cbsa=raw.get("cbsa", "").strip(),
        place=(place or "").strip(),
        effective_rate=rate,
        commercial_rate=commercial,
        industrial_rate=industrial,
        fixtures_exempt=raw.get("fixtures_exempt", "").strip().lower() == "true",
        metro_proxy=raw.get("metro_proxy", "").strip().lower() == "true",
        source_table=raw.get("source_table", "").strip(),
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
        commercial_rate=row.commercial_rate,
        industrial_rate=row.industrial_rate,
        fixtures_exempt=row.fixtures_exempt,
        source_table=row.source_table,
        cbsa=row.cbsa,
    )


def _metro(geo: GeoContext, code: str, rows: tuple[_Row, ...]) -> PropertyTaxResolution:
    """Average of the studied large cities that share ``code`` with the ZIP."""
    industrial = [row.industrial_rate for row in rows if row.industrial_rate is not None]
    return PropertyTaxResolution(
        zip_code=geo.zip_code,
        tier="cbsa",
        state=geo.state,
        county_fips=geo.county_fips,
        place=" / ".join(row.place for row in rows),
        effective_rate=math.fsum(row.effective_rate for row in rows) / len(rows),
        as_of=rows[0].as_of,
        citation=rows[0].citation,
        commercial_rate=math.fsum(row.commercial_rate for row in rows) / len(rows),
        industrial_rate=math.fsum(industrial) / len(industrial) if industrial else None,
        fixtures_exempt=all(row.fixtures_exempt for row in rows),
        source_table=";".join(sorted({row.source_table for row in rows})),
        cbsa=code,
    )
