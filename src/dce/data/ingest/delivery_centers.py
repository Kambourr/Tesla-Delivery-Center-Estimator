"""Existing Tesla delivery locations from a committed public snapshot.

Contract
--------
The live Find Us page is not on the public-data allowlist, so this loader
does not fetch it. ``load_delivery_centers`` reads the CSV committed at
``data/seed/tesla_delivery_centers_2026-11-08.csv``.

That file is the 2026-11-08 Bay Area delivery list used by the catchment
research (nine centers), plus the North San Jose hub, which was not on the
Find Us list that day (``location_type`` ``hub``). ``lat`` and ``lon`` are
Census 2024 Gazetteer ZCTA internal points for the center ZIP. Those are
the points the research distances were measured from. ``as_of`` is
``2026-11-08``.

No SQLite and no network. Persistence is :mod:`dce.data.persist`.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dce.config import bundled_seed_dir
from dce.data.ingest.http import IngestError

SNAPSHOT_FILENAME = "tesla_delivery_centers_2026-11-08.csv"
SNAPSHOT_AS_OF = "2026-11-08"
DELIVERY_CENTER_SOURCE_ID = "tesla_delivery_centers"
DELIVERY_CENTER_TTL_DAYS = 90
CITATION_URL = "https://www.tesla.com/findus/list/deliverycenters/United+States"
_LOCATION_TYPES = frozenset({"delivery", "store", "service", "hub", "possible_handover"})
_LICENSE = (
    "Tesla public Find Us delivery list as of 2026-11-08, limited to the Bay Area "
    "centers tabulated for the catchment research, plus the North San Jose hub. "
    "Coordinates are U.S. Census Bureau 2024 Gazetteer ZCTA internal points "
    "(public domain), not a rooftop geocode."
)
_COLUMNS = (
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
)


class DeliveryCenterError(IngestError):
    """The delivery-center snapshot could not be read."""


@dataclass(frozen=True)
class DeliveryCenter:
    """One Tesla location. ``as_of`` is an ISO date. Coordinates are decimal degrees."""

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


def delivery_center_license_note() -> str:
    """Return the ``source_registry`` license note for the snapshot."""
    return _LICENSE


def delivery_center_citation_url() -> str:
    """Return the Find Us page cited by the snapshot. This loader does not fetch it."""
    return CITATION_URL


def snapshot_path() -> Path:
    """Return the committed snapshot CSV under ``data/seed``."""
    return bundled_seed_dir() / SNAPSHOT_FILENAME


def load_delivery_centers(path: Path | None = None) -> tuple[DeliveryCenter, ...]:
    """Read the snapshot CSV. Does not use the network."""
    source = snapshot_path() if path is None else path
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeliveryCenterError(
            f"Could not read the delivery-center snapshot: {source}."
        ) from exc
    return parse_delivery_centers(text)


def parse_delivery_centers(text: str) -> tuple[DeliveryCenter, ...]:
    """Parse snapshot CSV text. Blank lines and ``#`` comments are ignored."""
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise DeliveryCenterError("The delivery-center snapshot has no rows.")
    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise DeliveryCenterError("The delivery-center snapshot has no header.")
    reader.fieldnames = [name.strip() for name in reader.fieldnames]
    header = tuple(reader.fieldnames)
    missing = [name for name in _COLUMNS if name not in header]
    if missing:
        raise DeliveryCenterError(
            "Delivery-center snapshot is missing columns: " + ", ".join(missing) + "."
        )
    rows: list[DeliveryCenter] = []
    seen: set[str] = set()
    for raw in reader:
        row = _parse_row(raw)
        if row.center_id in seen:
            raise DeliveryCenterError(f"Center {row.center_id} is listed more than once.")
        seen.add(row.center_id)
        rows.append(row)
    if not rows:
        raise DeliveryCenterError("The delivery-center snapshot has no rows.")
    return tuple(rows)


def _parse_row(raw: Iterable[tuple[str, str | None]] | dict[str, str | None]) -> DeliveryCenter:
    if not isinstance(raw, dict):
        raise DeliveryCenterError("Delivery-center row was not a CSV record.")
    center_id = _text(raw.get("center_id"), what="center_id")
    location_type = _text(raw.get("location_type"), what="location_type")
    if location_type not in _LOCATION_TYPES:
        raise DeliveryCenterError(
            f"Center {center_id} location_type must be one of "
            f"{', '.join(sorted(_LOCATION_TYPES))}, got {location_type!r}."
        )
    state = _text(raw.get("state"), what="state").upper()
    if len(state) != 2 or not state.isalpha():
        raise DeliveryCenterError(f"Center {center_id} state must be 2 letters, got {state!r}.")
    zip_code = _text(raw.get("zip"), what="zip")
    if len(zip_code) != 5 or not zip_code.isdigit():
        raise DeliveryCenterError(f"Center {center_id} ZIP must be 5 digits, got {zip_code!r}.")
    return DeliveryCenter(
        center_id=center_id,
        name=_text(raw.get("name"), what="name"),
        address=_text(raw.get("address"), what="address"),
        city=_text(raw.get("city"), what="city"),
        state=state,
        zip_code=zip_code,
        lat=_coordinate(center_id, raw.get("lat"), what="lat", low=-90.0, high=90.0),
        lon=_coordinate(center_id, raw.get("lon"), what="lon", low=-180.0, high=180.0),
        location_type=location_type,
        as_of=_iso_date(_text(raw.get("as_of"), what="as_of")),
        coordinate_basis=_text(raw.get("coordinate_basis"), what="coordinate_basis"),
    )


def _text(value: str | None, *, what: str) -> str:
    if value is None or value.strip() == "":
        raise DeliveryCenterError(f"Delivery-center {what} must be a non-empty string.")
    return value.strip()


def _coordinate(center_id: str, value: str | None, *, what: str, low: float, high: float) -> float:
    text = _text(value, what=what)
    try:
        number = float(text)
    except ValueError as exc:
        raise DeliveryCenterError(f"Center {center_id} {what} is not a number: {text!r}.") from exc
    if not math.isfinite(number) or number < low or number > high:
        raise DeliveryCenterError(f"Center {center_id} {what} is out of range: {text!r}.")
    return number


def _iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise DeliveryCenterError(
            f"Delivery-center as_of must be an ISO date, got {value!r}."
        ) from exc
