"""Regional price index for fit-out. Reads the bundled seed. No network.

BEA regional price parities, 2024. The fit-out index is the area's goods
RPP divided by the U.S. goods RPP, so a national ZIP stays at 1. The
all-items RPP is stored and not applied: housing rents dominate it, and
rent is already its own input. The utilities RPP is not applied either,
because electricity is an EIA price.

RSMeans city cost indexes are proprietary and are not used.

Fallback, first hit wins:

1. ``metro``. ``GeoContext.cbsa``, then the parent CBSA when ``cbsa`` is a
   metropolitan division (the same map OEWS uses).
2. ``state``. The state's goods RPP.
3. ``national``. Index 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from dce.data.ingest.bls_oews import OewsError, oews_area_for_cbsa
from dce.data.seed_csv import PublicSeedError, read_seed_csv
from dce.model.types import GeoContext


@dataclass(frozen=True)
class PriceIndexResolution:
    """Goods price parity used to scale fit-out, and the rung that supplied it."""

    zip_code: str
    tier: str
    geography_id: str
    name: str
    rpp_goods: float
    rpp_all_items: float
    fitout_index: float
    as_of: str
    citation: str


@dataclass(frozen=True)
class _Row:
    geography_type: str
    geography_id: str
    name: str
    rpp_goods: float
    rpp_all_items: float
    as_of: str
    citation: str


@dataclass(frozen=True)
class _Tables:
    metro: dict[str, _Row]
    state: dict[str, _Row]
    national: _Row


def resolve_price_index(geo: GeoContext) -> PriceIndexResolution:
    """Return the fit-out index for ``geo``."""
    tables = _load()
    us_goods = tables.national.rpp_goods
    for tier, key in _candidates(geo):
        table = tables.metro if tier == "metro" else tables.state
        row = table.get(key)
        if row is not None:
            return _resolution(geo, tier, row, us_goods)
    return _resolution(geo, "national", tables.national, us_goods)


def _candidates(geo: GeoContext) -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []
    if len(geo.cbsa) == 5 and geo.cbsa.isdigit():
        found.append(("metro", geo.cbsa))
        try:
            parent = oews_area_for_cbsa(geo.cbsa)
        except OewsError:
            parent = geo.cbsa
        if parent != geo.cbsa:
            found.append(("metro", parent))
    if geo.state:
        found.append(("state", geo.state))
    return tuple(found)


@lru_cache(maxsize=1)
def _load() -> _Tables:
    metro: dict[str, _Row] = {}
    state: dict[str, _Row] = {}
    national: _Row | None = None
    for raw in read_seed_csv("bea_rpp_2024.csv"):
        row = _parse(raw)
        if row.geography_type == "metro":
            metro[row.geography_id] = row
        elif row.geography_type == "state":
            state[row.geography_id] = row
        elif row.geography_type == "national":
            national = row
    if national is None or national.rpp_goods <= 0.0:
        raise PublicSeedError("Price-index seed has no national goods RPP.")
    return _Tables(metro=metro, state=state, national=national)


def _parse(raw: dict[str, str]) -> _Row:
    try:
        goods = float(raw["rpp_goods"])
        all_items = float(raw["rpp_all_items"])
    except (KeyError, ValueError) as exc:
        raise PublicSeedError(
            f"Price-index row {raw.get('geography_id')!r} is not usable."
        ) from exc
    if goods <= 0.0 or all_items <= 0.0:
        raise PublicSeedError(f"Price-index row {raw.get('geography_id')!r} is not positive.")
    return _Row(
        geography_type=raw.get("geography_type", "").strip(),
        geography_id=raw.get("geography_id", "").strip(),
        name=raw.get("name", "").strip(),
        rpp_goods=goods,
        rpp_all_items=all_items,
        as_of=raw.get("as_of", "").strip(),
        citation=raw.get("citation", "").strip(),
    )


def _resolution(geo: GeoContext, tier: str, row: _Row, us_goods: float) -> PriceIndexResolution:
    return PriceIndexResolution(
        zip_code=geo.zip_code,
        tier=tier,
        geography_id=row.geography_id,
        name=row.name,
        rpp_goods=row.rpp_goods,
        rpp_all_items=row.rpp_all_items,
        fitout_index=row.rpp_goods / us_goods,
        as_of=row.as_of,
        citation=row.citation,
    )
