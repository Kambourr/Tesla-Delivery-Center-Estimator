"""Construction-cost location factor for fit-out. Reads the bundled seed. No network.

The factor is the DoD MILCON area cost factor (ACF) from UFS 3-701-01, DoD
Facilities Pricing Guide, 6 June 2026, Table 4-1 CONUS (source date
2025-10-01). The Tri-Service ACF prices a market basket of 8 labor crafts,
18 materials, and 4 equipment items, weighted 63/35/2, then adjusts for
weather, seismic, climate, labor availability, overhead and profit,
logistics, and productivity. 1.00 is the average of the DoD's 96 base
cities, so a typical ZIP stays near the national fit-out cost.

``scripts/build_local_cost_seeds.py`` turns the DoD site list into county,
CBSA, and state rows (lower medians, so every value is one the DoD
published). The DoD says the MILCON ACF is for construction cost only; it
is applied here to the fit-out (tenant improvement) dollars and nothing else.

Fallback, first hit wins:

1. ``county``. The ZIP's county has DoD sites.
2. ``cbsa``. ``GeoContext.cbsa``, then the parent CBSA when ``cbsa`` is a
   metropolitan division: the lower median of that area's county factors.
3. ``state``. The lower median of the state's county factors.
4. ``bea_metro`` / ``bea_state``. BEA 2024 goods regional price parity over
   the U.S. goods parity (:mod:`dce.data.price_index`). Only reached for a
   place the DoD table does not cover, such as Puerto Rico.
5. ``national``. 1.00.

RSMeans and ENR city cost indexes are proprietary and are not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from dce.data.ingest.bls_oews import OewsError, oews_area_for_cbsa
from dce.data.price_index import PriceIndexResolution, resolve_price_index
from dce.data.seed_csv import PublicSeedError, read_seed_csv
from dce.model.types import GeoContext

ACF_SOURCE = "dod_ufs_3_701_01_2026"
BEA_SOURCE = "bea_rpp_goods_2024"
ACF_URL = "https://legacy.wbdg.org/FFC/DOD/UFC/ufs_3_701_01_2026_Data_Tables.xlsx"


@dataclass(frozen=True)
class ConstructionCostResolution:
    """Fit-out location factor for one ZIP and the rung that supplied it."""

    zip_code: str
    tier: str
    geography_id: str
    name: str
    fitout_index: float
    count: int
    source: str
    as_of: str
    citation: str
    bea: PriceIndexResolution

    @property
    def fallback(self) -> bool:
        """True unless the ZIP's own county has a DoD factor."""
        return self.tier != "county"


@dataclass(frozen=True)
class _Row:
    level: str
    geography_id: str
    name: str
    acf: float
    count: int
    as_of: str
    source: str
    citation: str


@dataclass(frozen=True)
class _Tables:
    county: dict[str, _Row]
    cbsa: dict[str, _Row]
    state: dict[str, _Row]
    national: _Row


def resolve_construction_cost(geo: GeoContext) -> ConstructionCostResolution:
    """Return the fit-out index for ``geo``."""
    tables = _load()
    bea = resolve_price_index(geo)
    county = tables.county.get(geo.county_fips)
    if county is not None:
        return _resolution(geo, "county", county, bea)
    for code in _cbsa_codes(geo.cbsa):
        row = tables.cbsa.get(code)
        if row is not None:
            return _resolution(geo, "cbsa", row, bea)
    state = tables.state.get(geo.state)
    if state is not None:
        return _resolution(geo, "state", state, bea)
    if bea.tier in {"metro", "state"}:
        return ConstructionCostResolution(
            zip_code=geo.zip_code,
            tier=f"bea_{bea.tier}",
            geography_id=bea.geography_id,
            name=bea.name,
            fitout_index=bea.fitout_index,
            count=0,
            source=BEA_SOURCE,
            as_of=bea.as_of,
            citation=bea.citation,
            bea=bea,
        )
    return _resolution(geo, "national", tables.national, bea)


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
    county: dict[str, _Row] = {}
    cbsa: dict[str, _Row] = {}
    state: dict[str, _Row] = {}
    national: _Row | None = None
    for raw in read_seed_csv("construction_cost_factor.csv"):
        row = _parse(raw)
        if row.level == "county":
            county[row.geography_id] = row
        elif row.level == "cbsa":
            cbsa[row.geography_id] = row
        elif row.level == "state":
            state[row.geography_id] = row
        elif row.level == "national":
            national = row
    if national is None:
        raise PublicSeedError("Construction-cost seed has no national factor.")
    return _Tables(county=county, cbsa=cbsa, state=state, national=national)


def _parse(raw: dict[str, str]) -> _Row:
    try:
        acf = float(raw["acf"])
        count = int(raw.get("count") or 0)
    except (KeyError, ValueError) as exc:
        raise PublicSeedError(
            f"Construction-cost row {raw.get('geography_id')!r} is not usable."
        ) from exc
    if acf <= 0.0:
        raise PublicSeedError(f"Construction-cost row {raw.get('geography_id')!r} is not positive.")
    return _Row(
        level=raw.get("level", "").strip(),
        geography_id=raw.get("geography_id", "").strip(),
        name=raw.get("name", "").strip(),
        acf=acf,
        count=count,
        as_of=raw.get("as_of", "").strip(),
        source=raw.get("source", "").strip() or ACF_SOURCE,
        citation=raw.get("citation", "").strip(),
    )


def _resolution(
    geo: GeoContext, tier: str, row: _Row, bea: PriceIndexResolution
) -> ConstructionCostResolution:
    return ConstructionCostResolution(
        zip_code=geo.zip_code,
        tier=tier,
        geography_id=row.geography_id,
        name=row.name,
        fitout_index=row.acf,
        count=row.count,
        source=row.source,
        as_of=row.as_of,
        citation=row.citation,
        bea=bea,
    )
