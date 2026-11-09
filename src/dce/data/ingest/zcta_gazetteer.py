"""Census Gazetteer ZCTA internal points (ZIP centroids).

Contract
--------
Allowlisted host: ``www2.census.gov``. The national file is the ZIP at
``.../{year}_Gazetteer/{year}_Gaz_zcta_national.zip``. ``parse_zcta_gazetteer``
reads the tab-separated text inside it (or a fixture with the same header).

``INTPTLAT`` and ``INTPTLONG`` are the internal point used as the ZCTA
centroid. ``as_of`` is ``{year}-01-01``, a vintage marker for that gazetteer
year, not the day Census posted the file. Stale after 18 months.

No SQLite. Tests pass a fixture and do not download the national file.
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass

from dce.data.ingest.http import IngestError, request_bytes
from dce.data.registry import TTL_18_MONTHS_DAYS

ZCTA_GAZETTEER_SOURCE_ID = "census_zcta_gazetteer"
GAZETTEER_TTL_DAYS = TTL_18_MONTHS_DAYS
GAZETTEER_YEAR = 2024
_LICENSE = (
    "U.S. Census Bureau Gazetteer Files, ZCTA internal points. Public domain (US government work)."
)


class GazetteerError(IngestError):
    """A Census ZCTA gazetteer file could not be read."""


@dataclass(frozen=True)
class ZctaCentroid:
    """One ZCTA internal point. ``vintage`` is the gazetteer year as text.

    ``land_sqmi`` is ``ALAND_SQMI`` when the file has that column. Density
    for the rent model is population divided by this area.
    """

    zcta: str
    lat: float
    lon: float
    vintage: str
    as_of: str
    land_sqmi: float | None = None


def gazetteer_license_note() -> str:
    """Return the ``source_registry`` license note for the gazetteer."""
    return _LICENSE


def gazetteer_url(year: int) -> str:
    """Return the national ZCTA gazetteer ZIP for ``year``."""
    vintage = _require_year(year)
    return (
        "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
        f"{vintage}_Gazetteer/{vintage}_Gaz_zcta_national.zip"
    )


def gazetteer_as_of(year: int) -> str:
    """Return the vintage marker ``{year}-01-01``."""
    return f"{_require_year(year)}-01-01"


def fetch_zcta_gazetteer(*, year: int = GAZETTEER_YEAR) -> tuple[ZctaCentroid, ...]:
    """Download and parse the national ZCTA gazetteer from ``census.gov``."""
    vintage = _require_year(year)
    url = gazetteer_url(vintage)
    try:
        payload = request_bytes(url, timeout=120)
    except IngestError as exc:
        raise GazetteerError(f"Census gazetteer request failed for {vintage}.") from exc
    return parse_gazetteer_zip(payload, year=vintage)


def parse_gazetteer_zip(payload: bytes, *, year: int) -> tuple[ZctaCentroid, ...]:
    """Unzip a gazetteer download and parse the single text member."""
    vintage = _require_year(year)
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise GazetteerError("Census gazetteer download was not a ZIP file.") from exc
    names = [name for name in archive.namelist() if name.endswith(".txt")]
    if len(names) != 1:
        raise GazetteerError("Census gazetteer ZIP should contain one text file.")
    text = archive.read(names[0]).decode("latin-1")
    return parse_zcta_gazetteer(text, year=vintage)


def parse_zcta_gazetteer(text: str, *, year: int) -> tuple[ZctaCentroid, ...]:
    """Parse Gazetteer text. The header names ``GEOID``, ``INTPTLAT``, and ``INTPTLONG``."""
    vintage = _require_year(year)
    as_of = gazetteer_as_of(vintage)
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise GazetteerError("ZCTA gazetteer text is empty.")
    header = [name.strip() for name in lines[0].split("\t")]
    try:
        geo_i = header.index("GEOID")
        lat_i = header.index("INTPTLAT")
        lon_i = header.index("INTPTLONG")
    except ValueError as exc:
        raise GazetteerError(
            "ZCTA gazetteer header must include GEOID, INTPTLAT, and INTPTLONG."
        ) from exc
    land_i = header.index("ALAND_SQMI") if "ALAND_SQMI" in header else None
    width = max(geo_i, lat_i, lon_i, land_i or 0)
    rows: list[ZctaCentroid] = []
    seen: set[str] = set()
    for line in lines[1:]:
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) <= width:
            raise GazetteerError("ZCTA gazetteer row is shorter than the header.")
        zcta = parts[geo_i]
        if len(zcta) != 5 or not zcta.isdigit():
            raise GazetteerError(f"ZCTA GEOID must be 5 digits, got {zcta!r}.")
        if zcta in seen:
            raise GazetteerError(f"ZCTA {zcta} is listed more than once.")
        seen.add(zcta)
        rows.append(
            ZctaCentroid(
                zcta=zcta,
                lat=_coordinate(zcta, parts[lat_i], what="INTPTLAT", low=-90.0, high=90.0),
                lon=_coordinate(zcta, parts[lon_i], what="INTPTLONG", low=-180.0, high=180.0),
                vintage=str(vintage),
                as_of=as_of,
                land_sqmi=None if land_i is None else _land(zcta, parts[land_i]),
            )
        )
    if not rows:
        raise GazetteerError("ZCTA gazetteer has no rows.")
    return tuple(rows)


def _require_year(year: int) -> int:
    if isinstance(year, bool) or not isinstance(year, int) or year < 2000 or year > 2100:
        raise GazetteerError(f"Gazetteer year must be a 4-digit year, got {year!r}.")
    return year


def _land(zcta: str, value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise GazetteerError(f"ZCTA {zcta} ALAND_SQMI is not a number: {value!r}.") from exc
    if not math.isfinite(number) or number < 0:
        raise GazetteerError(f"ZCTA {zcta} ALAND_SQMI is out of range: {value!r}.")
    return number


def _coordinate(zcta: str, value: str, *, what: str, low: float, high: float) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise GazetteerError(f"ZCTA {zcta} {what} is not a number: {value!r}.") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise GazetteerError(f"ZCTA {zcta} {what} is out of range: {value!r}.")
    return number
