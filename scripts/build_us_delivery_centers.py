"""Rebuild the US Tesla delivery-center seed from public sources.

The output is ``data/seed/tesla_delivery_centers_us_2026-11-08.csv``.
``dce.data.ingest.delivery_centers`` loads that file.
``tesla.com`` answers HTTP 403 to scripted requests. This script never
contacts it. Every input is a public copy or a public dataset:

1. Tesla's public Find Us US delivery-center list as captured by the
   Internet Archive Wayback Machine on 2024-12-14. That is the newest US
   capture. It is the list of record.
2. All the Places (CC0), run ``2026-10-17-13-32-31``. Its ``tesla`` spider
   reads the public Find Us sales and service locations. It shows whether a
   listed center still appeared in October 2026. It also finds sites whose
   own Tesla name says they deliver but that are not on the list.
3. OpenStreetMap through Overpass (ODbL). A Tesla ``shop=car`` or
   ``shop=car_repair`` near the address is a second check.
4. The U.S. Census Bureau batch geocoder (public domain) for coordinates.
   When it has no match, the Find Us point that All the Places recorded for
   the same center (same slug, or same house number and ZIP) is used. Then
   Nominatim (OSM, ODbL), at no more than one request a second. A row that
   none of these can place is dropped and reported. It is not guessed.

The ten Bay Area rows in ``tesla_delivery_centers_2026-11-08.csv`` (the
2026-11-08 research list and the North San Jose hub) are copied over
unchanged, with their ZCTA internal-point coordinates. The catchment
research distances were measured from those points.

Network hosts are allowlisted. Only https is used and redirects are
refused, as in ``dce.data.ingest.http``. Downloads are cached under
``data/cache/us_centers`` (gitignored). A rebuild from that cache does not
use the network. ``--refresh`` downloads them again.

Confidence:

- ``high``: on the Find Us delivery list and present in the 2026-10-17 All
  the Places run, or a row from the 2026-11-08 research list.
- ``medium``: on the delivery list, not in the 2026 run, but an OSM Tesla
  shop is within 300 m. The North San Jose hub is also ``medium`` because
  it was not on the Find Us list.
- ``low``: on the 2024 delivery list with no 2026 evidence, or a 2026 Tesla
  site whose own name or Find Us slug says "delivery" but that is not on any
  delivery list (``location_type`` ``possible_handover``).
"""

from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import re
import sys
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from http.client import HTTPMessage
from pathlib import Path
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
CACHE_DIR = ROOT / "data" / "cache" / "us_centers"
OUTPUT_NAME = "tesla_delivery_centers_us_2026-11-08.csv"
BAY_AREA_NAME = "tesla_delivery_centers_2026-11-08.csv"
SNAPSHOT_AS_OF = "2026-11-08"

FINDUS_CAPTURE = "20241214220441"
FINDUS_URL = (
    f"https://web.archive.org/web/{FINDUS_CAPTURE}id_/"
    "https://www.tesla.com/findus/list/deliverycenters/United+States"
)
ATP_RUN = "2026-10-17-13-32-31"
ATP_URL = f"https://alltheplaces-data.openaddresses.io/runs/{ATP_RUN}/output/tesla.geojson"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = (
    "[out:json][timeout:150];"
    'area["ISO3166-1"="US"][admin_level=2]->.us;'
    '(nwr["brand:wikidata"="Q478214"]["shop"~"^(car|car_repair)$"](area.us);'
    'nwr["brand"="Tesla"]["shop"~"^(car|car_repair)$"](area.us);'
    'nwr["name"~"^Tesla"]["shop"~"^(car|car_repair)$"](area.us););'
    "out center tags;"
)
CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

SOURCE_FINDUS = "tesla_findus_wayback_20241214"
SOURCE_ATP = "alltheplaces_tesla_20261017"
SOURCE_OSM = "osm_overpass_20261108"
SOURCE_RESEARCH = "dce_research_20261108"

BASIS_CENSUS = "census_geocoder_current"
BASIS_NOMINATIM = "nominatim_osm"
BASIS_NOMINATIM_STREET = "nominatim_osm_street"
BASIS_ATP = "alltheplaces_findus_point"

ALLOWED_HOSTS = frozenset(
    {
        "web.archive.org",
        "alltheplaces-data.openaddresses.io",
        "overpass-api.de",
        "geocoding.geo.census.gov",
        "nominatim.openstreetmap.org",
    }
)
USER_AGENT = (
    "delivery-center-estimator/0.0 "
    "(+https://github.com/Kambourr/Tesla-Delivery-Center-Estimator; seed rebuild)"
)
NOMINATIM_DELAY_SECONDS = 1.1
MAX_BYTES = 20_000_000
MATCH_METERS = 300.0

COLUMNS = (
    "center_id",
    "name",
    "address",
    "city",
    "state",
    "zip",
    "lat",
    "lon",
    "location_type",
    "as_of",
    "coordinate_basis",
    "source",
    "confidence",
)

STATE_CODES = {
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


class BuildError(Exception):
    """An input could not be fetched or parsed."""


@dataclass(frozen=True)
class FindUsRow:
    """One entry on the Find Us delivery-center list."""

    slug: str
    title: str
    street: str
    city: str
    state: str
    zip_code: str


@dataclass(frozen=True)
class Site:
    """A Tesla point from All the Places or OpenStreetMap."""

    ref: str
    name: str
    street: str
    city: str
    state: str
    zip_code: str
    lat: float
    lon: float


@dataclass(frozen=True)
class SeedRow:
    """One output row. Field order matches :data:`COLUMNS`."""

    center_id: str
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    lat: float
    lon: float
    location_type: str
    as_of: str
    coordinate_basis: str
    source: str
    confidence: str


# --------------------------------------------------------------------------- network


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        del req, fp, msg, headers
        raise BuildError(f"Refusing HTTP {code} redirect to {urlparse(newurl).hostname}.")


def require_allowed(url: str) -> None:
    """Raise unless ``url`` is https on :data:`ALLOWED_HOSTS` with no credentials."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_HOSTS:
        raise BuildError(f"Refusing {parsed.scheme}://{host}: not on the seed-build allowlist.")
    if parsed.username is not None or parsed.password is not None:
        raise BuildError("Refusing a URL that embeds credentials.")


def fetch(
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 300.0,
) -> bytes:
    """Fetch one allowlisted URL. POST when ``body`` is given."""
    require_allowed(url)
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    method = "GET" if body is None else "POST"
    request = Request(url, data=body, headers=request_headers, method=method)
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = bytes(response.read(MAX_BYTES + 1))
    except HTTPError as exc:
        raise BuildError(f"{urlparse(url).hostname} returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise BuildError(f"Could not reach {urlparse(url).hostname}: {exc.reason}.") from exc
    if len(payload) > MAX_BYTES:
        raise BuildError(f"{urlparse(url).hostname} response exceeded {MAX_BYTES} bytes.")
    return payload


def cached(path: Path, refresh: bool, download: Callable[[], bytes]) -> bytes:
    """Return the cached bytes at ``path``, downloading them when absent or refreshing."""
    if path.exists() and not refresh:
        return path.read_bytes()
    payload = download()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return payload


# --------------------------------------------------------------------------- parsing

_HEADER = re.compile(r'<h4 class="subregion_header">(.*?)</h4>', re.S)
_ENTRY = re.compile(
    r'href="/findus/location/deliverycenter/([^"]+)"><p>(.*?)</p></a></div>'
    r'((?:<div class="subregion_location_addressLine1">.*?</div>)+)',
    re.S,
)
_LINE = re.compile(r'<div class="subregion_location_addressLine1">(.*?)</div>', re.S)
_CITY_LINE = re.compile(r"^(?P<city>.+?),\s*(?P<state>[A-Za-z]{2})\s+(?P<zip>\d{5})(?:-\d{4})?$")


def parse_findus_list(text: str) -> list[FindUsRow]:
    """Parse the Find Us delivery-center list page. Raises on an empty or odd page."""
    rows: list[FindUsRow] = []
    headers = list(_HEADER.finditer(text))
    if not headers:
        raise BuildError("The Find Us capture has no state headers.")
    for index, header in enumerate(headers):
        state_name = _clean(header.group(1))
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        state = STATE_CODES.get(state_name)
        if state is None:
            raise BuildError(f"Unknown state header in the Find Us capture: {state_name!r}.")
        for entry in _ENTRY.finditer(text, header.end(), end):
            lines = [_clean(line) for line in _LINE.findall(entry.group(3))]
            lines = [line for line in lines if line]
            if len(lines) < 2:
                raise BuildError(f"Find Us entry {entry.group(1)} has no street line.")
            match = _CITY_LINE.match(lines[-1])
            if match is None:
                raise BuildError(f"Find Us entry {entry.group(1)} city line is {lines[-1]!r}.")
            if match.group("state").upper() != state:
                raise BuildError(f"Find Us entry {entry.group(1)} is not in {state}.")
            rows.append(
                FindUsRow(
                    slug=entry.group(1),
                    title=_clean(entry.group(2)),
                    street=clean_street(lines[:-1], lines[-1]),
                    city=tidy_case(match.group("city")),
                    state=state,
                    zip_code=match.group("zip"),
                )
            )
    if not rows:
        raise BuildError("The Find Us capture has no delivery centers.")
    return rows


def clean_street(lines: Sequence[str], city_line: str) -> str:
    """Join street lines, drop a repeated city line and a doubled house number."""
    cleaned: list[str] = []
    for line in lines:
        city_part = city_line.strip()
        if line.endswith(city_part) and line != city_part:
            line = line[: -len(city_part)].rstrip(" ,")
        line = re.sub(r"^(\d+)\s+\1\b", r"\1", line).rstrip(" .")
        if line:
            cleaned.append(tidy_case(line))
    return ", ".join(cleaned)


def tidy_case(text: str) -> str:
    """Title-case a value only when the source printed it in all capitals."""
    text = " ".join(text.split())
    if text.isupper():
        return " ".join(_title_word(word) for word in text.split())
    return text


def _title_word(word: str) -> str:
    if re.fullmatch(r"(?:[NSEW]|NE|NW|SE|SW)", word):
        return word
    if re.fullmatch(r"\d+(?:ST|ND|RD|TH)", word):
        return word.lower()
    return word.capitalize()


def _clean(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def parse_atp(text: str) -> list[Site]:
    """Return US Tesla sales and service points from an All the Places GeoJSON file."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildError("All the Places output is not JSON.") from exc
    features = data.get("features") if isinstance(data, dict) else None
    if not isinstance(features, list):
        raise BuildError("All the Places output has no features list.")
    sites: list[Site] = []
    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if props.get("addr:country") != "US" or props.get("shop") not in ("car", "car_repair"):
            continue
        coords = geometry.get("coordinates")
        if geometry.get("type") != "Point" or not isinstance(coords, list) or len(coords) < 2:
            continue
        sites.append(
            Site(
                ref=str(props.get("ref", "")),
                name=str(props.get("name", "")),
                street=str(props.get("addr:street_address", "")),
                city=str(props.get("addr:city", "")),
                state=str(props.get("addr:state", "")).upper(),
                zip_code=str(props.get("addr:postcode", ""))[:5],
                lat=float(coords[1]),
                lon=float(coords[0]),
            )
        )
    if not sites:
        raise BuildError("All the Places output has no US Tesla sales or service points.")
    return sites


def parse_overpass(text: str) -> list[Site]:
    """Return Tesla shop points from an Overpass JSON answer."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildError("Overpass did not return JSON.") from exc
    elements = data.get("elements") if isinstance(data, dict) else None
    if not isinstance(elements, list):
        raise BuildError("Overpass answer has no elements.")
    sites: list[Site] = []
    for element in elements:
        tags = element.get("tags") or {}
        point = element if "lat" in element else element.get("center") or {}
        if "lat" not in point or "lon" not in point:
            continue
        street = " ".join(
            part for part in (tags.get("addr:housenumber", ""), tags.get("addr:street", "")) if part
        )
        sites.append(
            Site(
                ref=f"{element.get('type', '')}/{element.get('id', '')}",
                name=str(tags.get("name", "")),
                street=street,
                city=str(tags.get("addr:city", "")),
                state=str(tags.get("addr:state", "")).upper(),
                zip_code=str(tags.get("addr:postcode", ""))[:5],
                lat=float(point["lat"]),
                lon=float(point["lon"]),
            )
        )
    return sites


def census_batch_body(rows: Sequence[FindUsRow], boundary: str) -> bytes:
    """Return a multipart body for the Census batch geocoder."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for index, row in enumerate(rows):
        writer.writerow([index, row.street, row.city, row.state, row.zip_code])
    parts = [
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="benchmark"\r\n\r\n'
        "Public_AR_Current\r\n",
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="addressFile"; filename="centers.csv"\r\n'
        "Content-Type: text/csv\r\n\r\n" + buffer.getvalue() + "\r\n",
        f"--{boundary}--\r\n",
    ]
    return "".join(parts).encode("utf-8")


def parse_census_batch(text: str) -> dict[int, tuple[float, float]]:
    """Map batch row id to ``(lat, lon)`` for rows the Census geocoder matched."""
    points: dict[int, tuple[float, float]] = {}
    for record in csv.reader(io.StringIO(text)):
        if len(record) < 6 or record[2] != "Match":
            continue
        lon_text, _, lat_text = record[5].partition(",")
        try:
            points[int(record[0])] = (float(lat_text), float(lon_text))
        except ValueError:
            continue
    return points


def parse_nominatim(text: str) -> tuple[float, float, str] | None:
    """Return the first Nominatim hit as ``(lat, lon, coordinate_basis)``, or ``None``.

    A hit on a road rather than a building or address point is street-level
    only, so its basis is ``nominatim_osm_street``.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BuildError("Nominatim did not return JSON.") from exc
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    basis = BASIS_NOMINATIM_STREET if first.get("category") == "highway" else BASIS_NOMINATIM
    return float(first["lat"]), float(first["lon"]), basis


def read_bay_area(path: Path) -> list[dict[str, str]]:
    """Read the committed Bay Area research rows."""
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return [dict(row) for row in csv.DictReader(lines)]


# --------------------------------------------------------------------------- merge


def meters_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def house_number(street: str) -> str:
    match = re.match(r"\s*(\d+)", street)
    return match.group(1) if match else ""


def same_place(
    row: FindUsRow, point: tuple[float, float] | None, site: Site, *, by_slug: bool
) -> bool:
    """Whether ``site`` is the Find Us center ``row``."""
    if by_slug and site.ref.rsplit("-", 1)[0].lower() == row.slug.lower():
        return True
    number = house_number(row.street)
    if number and site.zip_code == row.zip_code and house_number(site.street) == number:
        return True
    if point is None:
        return False
    return meters_between(point[0], point[1], site.lat, site.lon) <= MATCH_METERS


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_rows(
    findus: Sequence[FindUsRow],
    points: dict[int, tuple[float, float, str]],
    atp: Sequence[Site],
    osm: Sequence[Site],
    bay_area: Sequence[dict[str, str]],
) -> tuple[list[SeedRow], list[str]]:
    """Merge the inputs into seed rows. Returns rows and human-readable notes."""
    notes: list[str] = []
    bay_by_zip = {row["zip"]: row for row in bay_area}
    rows: list[SeedRow] = []
    for raw in bay_area:
        confidence = "medium" if raw["location_type"] == "hub" else "high"
        source = SOURCE_RESEARCH
        if any(item.zip_code == raw["zip"] for item in findus):
            source += ";" + SOURCE_FINDUS
        rows.append(
            SeedRow(
                center_id=raw["center_id"],
                name=raw["name"],
                address=raw["address"],
                city=raw["city"],
                state=raw["state"],
                zip_code=raw["zip"],
                lat=float(raw["lat"]),
                lon=float(raw["lon"]),
                location_type=raw["location_type"],
                as_of=SNAPSHOT_AS_OF,
                coordinate_basis=raw["coordinate_basis"],
                source=source,
                confidence=confidence,
            )
        )
    matched_atp: set[str] = set()
    for index, item in enumerate(findus):
        point_and_basis = points.get(index)
        point = None if point_and_basis is None else point_and_basis[:2]
        atp_hits = [site for site in atp if same_place(item, point, site, by_slug=True)]
        matched_atp.update(site.ref.rsplit("-", 1)[0] for site in atp_hits)
        if item.state == "CA" and item.zip_code in bay_by_zip:
            continue
        if point_and_basis is None:
            notes.append(f"dropped {item.slug}: no geocode for {item.street}, {item.city}")
            continue
        osm_hit = any(same_place(item, point, site, by_slug=False) for site in osm)
        sources = [SOURCE_FINDUS]
        if atp_hits:
            sources.append(SOURCE_ATP)
        if osm_hit:
            sources.append(SOURCE_OSM)
        confidence = "high" if atp_hits else "medium" if osm_hit else "low"
        lat, lon, basis = point_and_basis
        rows.append(
            SeedRow(
                center_id="",
                name=f"Tesla Delivery {item.city}",
                address=item.street,
                city=item.city,
                state=item.state,
                zip_code=item.zip_code,
                lat=round(lat, 6),
                lon=round(lon, 6),
                location_type="delivery",
                as_of=SNAPSHOT_AS_OF,
                coordinate_basis=basis,
                source=";".join(sources),
                confidence=confidence,
            )
        )
    known = {(row.zip_code, house_number(row.address)) for row in rows}
    for slug, sites in _delivery_named(atp).items():
        if slug.lower() in {ref.lower() for ref in matched_atp}:
            continue
        site = sites[0]
        if (site.zip_code, house_number(site.street)) in known:
            continue
        osm_hit = any(
            meters_between(site.lat, site.lon, other.lat, other.lon) <= MATCH_METERS
            for other in osm
        )
        sources = [SOURCE_ATP] + ([SOURCE_OSM] if osm_hit else [])
        rows.append(
            SeedRow(
                center_id="",
                name=f"Tesla {tidy_case(site.city)} (possible delivery)",
                address=tidy_case(site.street),
                city=tidy_case(site.city),
                state=site.state,
                zip_code=site.zip_code,
                lat=round(site.lat, 6),
                lon=round(site.lon, 6),
                location_type="possible_handover",
                as_of=SNAPSHOT_AS_OF,
                coordinate_basis=BASIS_ATP,
                source=";".join(sources),
                confidence="low",
            )
        )
        notes.append(f"possible handover from All the Places: {slug} ({site.name})")
    return assign_ids(rows), notes


def _delivery_named(atp: Iterable[Site]) -> dict[str, list[Site]]:
    found: dict[str, list[Site]] = {}
    for site in atp:
        slug = site.ref.rsplit("-", 1)[0]
        if "deliver" in f"{slug} {site.name}".lower():
            found.setdefault(slug, []).append(site)
    return dict(sorted(found.items()))


def assign_ids(rows: Sequence[SeedRow]) -> list[SeedRow]:
    """Give new rows ``<city>-<state>`` ids, adding the house number on a clash."""
    taken = {row.center_id for row in rows if row.center_id}
    base_counts = Counter(
        f"{slugify(row.city)}-{row.state.lower()}" for row in rows if not row.center_id
    )
    out: list[SeedRow] = []
    for row in rows:
        if row.center_id:
            out.append(row)
            continue
        base = f"{slugify(row.city)}-{row.state.lower()}"
        center_id = base
        if base_counts[base] > 1 or base in taken:
            center_id = f"{base}-{house_number(row.address) or len(taken)}"
        if center_id in taken:
            raise BuildError(f"Two centers would share the id {center_id}.")
        taken.add(center_id)
        name = row.name
        if base_counts[base] > 1 and row.location_type == "delivery":
            name = f"{row.name} - {row.address.split(',')[0]}"
        out.append(replace(row, center_id=center_id, name=name))
    return sorted(out, key=lambda row: (row.state, row.city, row.center_id))


def render_csv(rows: Sequence[SeedRow]) -> str:
    """Render the seed CSV, header comments included."""
    buffer = io.StringIO()
    buffer.write(
        "# US Tesla delivery locations. Built by scripts/build_us_delivery_centers.py.\n"
        "# Sources and access dates: docs/DATA_SOURCES.md section 10. Public data only.\n"
        "# Bay Area research rows keep Census 2024 Gazetteer ZCTA internal points.\n"
    )
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.center_id,
                row.name,
                row.address,
                row.city,
                row.state,
                row.zip_code,
                f"{row.lat:.6f}".rstrip("0").rstrip("."),
                f"{row.lon:.6f}".rstrip("0").rstrip("."),
                row.location_type,
                row.as_of,
                row.coordinate_basis,
                row.source,
                row.confidence,
            ]
        )
    return buffer.getvalue()


# --------------------------------------------------------------------------- main


def first_points(
    findus: Sequence[FindUsRow],
    census: dict[int, tuple[float, float]],
    atp: Sequence[Site],
) -> dict[int, tuple[float, float, str]]:
    """Census matches, then the All the Places point for the same center. No network."""
    points = {index: (lat, lon, BASIS_CENSUS) for index, (lat, lon) in census.items()}
    for index, row in enumerate(findus):
        if index in points:
            continue
        site = next((site for site in atp if same_place(row, None, site, by_slug=True)), None)
        if site is not None:
            points[index] = (site.lat, site.lon, BASIS_ATP)
    return points


def geocode(
    findus: Sequence[FindUsRow], atp: Sequence[Site], cache: Path, refresh: bool
) -> dict[int, tuple[float, float, str]]:
    """Census batch, then the matching All the Places point, then Nominatim.

    Nominatim is called one request at a time, no faster than
    :data:`NOMINATIM_DELAY_SECONDS`, and only for rows the first two miss.
    """
    boundary = f"dce-{uuid.uuid4().hex}"
    census_text = cached(
        cache / f"census_batch_{FINDUS_CAPTURE}.csv",
        refresh,
        lambda: fetch(
            CENSUS_BATCH_URL,
            body=census_batch_body(findus, boundary),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        ),
    ).decode("utf-8", errors="replace")
    points = first_points(findus, parse_census_batch(census_text), atp)
    nominatim_cache = cache / "nominatim"
    for index, row in enumerate(findus):
        if index in points:
            continue
        query = urlencode(
            {
                "street": row.street.split(",")[0],
                "city": row.city,
                "state": row.state,
                "postalcode": row.zip_code,
                "countrycodes": "us",
                "format": "jsonv2",
                "limit": "1",
            }
        )
        path = nominatim_cache / f"{slugify(row.slug)}.json"
        fresh = refresh or not path.exists()
        text = cached(path, refresh, lambda q=query: fetch(f"{NOMINATIM_URL}?{q}")).decode()
        if fresh:
            time.sleep(NOMINATIM_DELAY_SECONDS)
        hit = parse_nominatim(text)
        if hit is not None:
            points[index] = hit
    return points


def main(argv: list[str] | None = None) -> int:
    """Rebuild the US delivery-center seed CSV."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--out", type=Path, default=SEED_DIR / OUTPUT_NAME)
    parser.add_argument("--refresh", action="store_true", help="Download every input again.")
    args = parser.parse_args(argv)
    cache: Path = args.cache_dir
    try:
        findus = parse_findus_list(
            cached(
                cache / "findus_wayback_20241214.html", args.refresh, lambda: fetch(FINDUS_URL)
            ).decode("utf-8", errors="replace")
        )
        atp = parse_atp(
            cached(
                cache / f"atp_tesla_{ATP_RUN}.geojson", args.refresh, lambda: fetch(ATP_URL)
            ).decode("utf-8")
        )
        osm = parse_overpass(
            cached(
                cache / "overpass_tesla_shops.json",
                args.refresh,
                lambda: fetch(
                    OVERPASS_URL,
                    body=urlencode({"data": OVERPASS_QUERY}).encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                ),
            ).decode("utf-8")
        )
        points = geocode(findus, atp, cache, args.refresh)
        rows, notes = build_rows(findus, points, atp, osm, read_bay_area(SEED_DIR / BAY_AREA_NAME))
    except (BuildError, OSError) as exc:
        print(f"build_us_delivery_centers: {exc}", file=sys.stderr)
        return 1
    args.out.write_text(render_csv(rows), encoding="utf-8")
    for note in notes:
        print(note)
    states = Counter(row.state for row in rows)
    print(
        f"Wrote {len(rows)} rows in {len(states)} states to {args.out}: "
        + ", ".join(f"{state} {count}" for state, count in sorted(states.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
