"""Census TIGER and cartographic geometry.

Contract
--------
Allowlisted host: ``census.gov``. ZCTA polygons come from the cartographic
boundary file. Census stopped publishing a new national ZCTA cartographic
file after 2020 (the 2024 GENZ directory has no ZCTA zip), and the 2024
gazetteer still says ZCTAs follow 2020 tabulation blocks. The file in use
is ``cb_2020_us_zcta520_500k.zip``.

MapLibre draws a national file of about 33,000 polygons fastest as vector
tiles (PMTiles): only the tiles in view are decoded. A single GeoJSON of
the same polygons is parsed all at once. ``simplify_zcta_geojson`` writes
the GeoJSON a fixture or a tile build can consume. The national PMTiles
archive is produced by ``scripts/build_zcta_boundaries.py``. Do not commit
that archive. A Bay Area GeoJSON fixture is the committed offline sample.

No API key. This module does not open SQLite. Block-group download is still
a stub.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dce.data.ingest.http import IngestError, request_bytes

ZCTA_BOUNDARY_YEAR = 2020
ZCTA_SIMPLIFY_DEGREES = 0.001
_BOUNDARY_MAX_BYTES = 80_000_000
_CODE_COLUMNS = ("ZCTA5CE20", "ZCTA5CE10", "GEOID20", "GEOID")


@dataclass(frozen=True)
class GeometryFetch:
    """One simplified geometry extract. ``path`` is where the bytes were written."""

    geoid: str
    path: Path


class BoundaryError(IngestError):
    """A ZCTA boundary file could not be simplified."""


def cartographic_zcta_url(year: int = ZCTA_BOUNDARY_YEAR) -> str:
    """Return the national 1:500,000 ZCTA cartographic boundary zip."""
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise BoundaryError(f"Boundary year must be a 4-digit year, got {year!r}.")
    return f"https://www2.census.gov/geo/tiger/GENZ{year}/shp/cb_{year}_us_zcta520_500k.zip"


def fetch_zcta_boundaries(destination: Path, *, year: int = ZCTA_BOUNDARY_YEAR) -> Path:
    """Download the cartographic ZCTA zip to ``destination``. No simplification."""
    url = cartographic_zcta_url(year)
    try:
        payload = request_bytes(url, timeout=180, max_bytes=_BOUNDARY_MAX_BYTES)
    except IngestError as exc:
        raise BoundaryError(f"Census ZCTA boundary download failed for {year}.") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


def simplify_zcta_geojson(
    shapefile: Path,
    *,
    zctas: frozenset[str] | None = None,
    tolerance_degrees: float = ZCTA_SIMPLIFY_DEGREES,
) -> dict[str, object]:
    """Return a GeoJSON FeatureCollection, Douglas-Peucker simplified.

    ``tolerance_degrees`` is the Shapely tolerance in the file's degree
    units. ``0.001`` is about 111 meters. Topology is preserved.
    ``zctas`` limits the features. ``None`` keeps every ZCTA in the file.
    The only property kept is ``zcta``.
    """
    if not shapefile.exists():
        raise BoundaryError(f"ZCTA boundary file was not found: {shapefile}.")
    if (
        isinstance(tolerance_degrees, bool)
        or not isinstance(tolerance_degrees, (int, float))
        or tolerance_degrees < 0
    ):
        raise BoundaryError(f"Tolerance must be >= 0 degrees, got {tolerance_degrees!r}.")
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - geopandas is a project dependency
        raise BoundaryError("geopandas is required to read ZCTA boundaries.") from exc
    frame = gpd.read_file(shapefile)
    code_column = next((name for name in _CODE_COLUMNS if name in frame.columns), None)
    if code_column is None:
        raise BoundaryError("ZCTA boundary file has no ZCTA code column.")
    if zctas is not None:
        frame = frame[frame[code_column].isin(zctas)]
    if frame.empty:
        raise BoundaryError("ZCTA boundary subset has no features.")
    frame = frame.copy()
    if frame.crs is not None:
        frame = frame.to_crs(4326)
    frame["geometry"] = frame.geometry.simplify(tolerance_degrees, preserve_topology=True)
    frame = frame[~frame.geometry.is_empty]
    frame["zcta"] = frame[code_column].astype(str).str.zfill(5)
    slim = frame[["zcta", "geometry"]]
    parsed: object = json.loads(slim.to_json())
    if not isinstance(parsed, dict):
        raise BoundaryError("Boundary GeoJSON was not an object.")
    parsed.pop("crs", None)
    return parsed


def write_geojson(features: dict[str, object], path: Path) -> Path:
    """Write a FeatureCollection. Returns ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(features, separators=(",", ":")), encoding="utf-8")
    return path


def fetch_county_block_groups(state_fips: str, county_fips: str) -> GeometryFetch:
    """Download and simplify one county's block groups. Not implemented in M0."""
    raise NotImplementedError("dce.data.ingest.census_geo.fetch_county_block_groups is a stub (M0)")
