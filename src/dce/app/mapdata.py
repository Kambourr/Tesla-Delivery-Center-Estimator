"""ZIP boundaries and Tesla center markers for the map.

No network. Polygons come from a GeoJSON file. Centers come from the
committed public snapshot. The national ZCTA file is not required: a
missing or partial file still returns the centers, and the page draws
whatever polygons did load.
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache
from pathlib import Path

from dce.config import bundled_seed_dir
from dce.data.ingest.delivery_centers import (
    DeliveryCenterError,
    load_us_delivery_centers,
)

# Property names a Census extract is likely to use, plus our fixture's ``zip``.
_ZIP_KEYS = ("zip", "zcta", "ZCTA5CE20", "ZCTA5CE10", "GEOID20", "GEOID10")
_MARKER_TYPES = frozenset({"delivery", "hub"})


class MapDataError(ValueError):
    """The ZCTA GeoJSON could not be read."""


def load_map(zcta_path: Path) -> dict[str, object]:
    """Return a normalized FeatureCollection and the center markers.

    Each feature has ``properties.zip`` (5 digits), ``properties.lat``, and
    ``properties.lon``. ``id`` is the ZIP so MapLibre feature-state can
    address it. Centers are delivery locations and delivery hubs.
    """
    collection = load_zcta(zcta_path)
    return {"zcta": collection, "centers": list(load_centers())}


@lru_cache(maxsize=4)
def load_zcta(path: Path) -> dict[str, object]:
    """Read and normalize one ZCTA GeoJSON file."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise MapDataError(f"Could not read ZCTA shapes: {path}.") from exc
    except json.JSONDecodeError as exc:
        raise MapDataError(f"ZCTA file is not valid JSON: {path}.") from exc
    return _normalize_collection(raw, path)


@lru_cache(maxsize=1)
def load_centers() -> tuple[dict[str, object], ...]:
    """Return delivery-center and hub markers from the US snapshot."""
    try:
        rows = load_us_delivery_centers()
    except DeliveryCenterError as exc:
        raise MapDataError(str(exc)) from exc
    markers = [
        {
            "center_id": row.center_id,
            "name": row.name,
            "city": row.city,
            "state": row.state,
            "zip_code": row.zip_code,
            "lat": row.lat,
            "lon": row.lon,
            "location_type": row.location_type,
        }
        for row in rows
        if row.location_type in _MARKER_TYPES
    ]
    return tuple(sorted(markers, key=lambda item: str(item["center_id"])))


def zip_index(collection: dict[str, object]) -> list[dict[str, object]]:
    """Return ``zip``, ``lat``, and ``lon`` for every feature, sorted by ZIP.

    A Gazetteer internal point replaces the ring average when the seed has
    that ZCTA.
    """
    features = collection.get("features")
    if not isinstance(features, list):
        return []
    centroids = _centroids()
    index: list[dict[str, object]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties")
        if not isinstance(props, dict):
            continue
        zip_code = str(props.get("zip") or "")
        point = centroids.get(zip_code)
        lat: object = point[0] if point is not None else props.get("lat")
        lon: object = point[1] if point is not None else props.get("lon")
        index.append({"zip": zip_code, "lat": lat, "lon": lon})
    return index


def nationwide_zip_index() -> list[dict[str, object]]:
    """Return every 2024 Gazetteer internal point, for search on the PMTiles map."""
    return [
        {"zip": zcta, "lat": lat, "lon": lon} for zcta, (lat, lon) in sorted(_centroids().items())
    ]


def lookup_centroid(zcta: str) -> tuple[float, float] | None:
    """Return the 2024 Gazetteer internal point for one ZCTA, if the seed has it."""
    return _centroids().get(zcta)


@lru_cache(maxsize=1)
def _centroids() -> dict[str, tuple[float, float]]:
    path = bundled_seed_dir() / "zcta_centroid_2024.csv"
    found: dict[str, tuple[float, float]] = {}
    if not path.is_file():
        return found
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return found
    for row in csv.DictReader(text.splitlines()):
        zcta = (row.get("zcta") or "").strip()
        if len(zcta) != 5 or not zcta.isdigit():
            continue
        try:
            found[zcta] = (float(row["lat"]), float(row["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _normalize_collection(raw: object, path: Path) -> dict[str, object]:
    if not isinstance(raw, dict) or raw.get("type") != "FeatureCollection":
        raise MapDataError(f"ZCTA file must be a FeatureCollection: {path}.")
    features = raw.get("features")
    if not isinstance(features, list):
        raise MapDataError(f"ZCTA file has no features: {path}.")
    normalized: list[dict[str, object]] = []
    seen: set[str] = set()
    for feature in features:
        item = _normalize_feature(feature)
        if item is None:
            continue
        zip_code = str(item["id"])
        if zip_code in seen:
            continue
        seen.add(zip_code)
        normalized.append(item)
    if not normalized:
        raise MapDataError(f"ZCTA file has no ZIP polygons: {path}.")
    normalized.sort(key=lambda item: str(item["id"]))
    return {"type": "FeatureCollection", "features": normalized}


def _normalize_feature(feature: object) -> dict[str, object] | None:
    if not isinstance(feature, dict):
        return None
    geometry = feature.get("geometry")
    props_raw = feature.get("properties")
    props = props_raw if isinstance(props_raw, dict) else {}
    zip_code = _zip_property(props)
    if zip_code is None or not isinstance(geometry, dict):
        return None
    lat, lon = _lat_lon(props, geometry)
    return {
        "type": "Feature",
        "id": zip_code,
        "properties": {"zip": zip_code, "lat": lat, "lon": lon},
        "geometry": geometry,
    }


def _zip_property(props: dict[str, object]) -> str | None:
    for key in _ZIP_KEYS:
        value = props.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if len(text) == 5 and text.isdigit():
            return text
    return None


def _lat_lon(
    props: dict[str, object], geometry: dict[str, object]
) -> tuple[float | None, float | None]:
    lat = _number(props.get("lat"))
    lon = _number(props.get("lon"))
    if lat is not None and lon is not None:
        return lat, lon
    points = _points(geometry.get("coordinates"))
    if not points:
        return lat, lon
    return (
        sum(point[1] for point in points) / len(points),
        sum(point[0] for point in points) / len(points),
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _points(value: object) -> list[tuple[float, float]]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    if isinstance(first, (int, float)) and not isinstance(first, bool) and len(value) >= 2:
        second = value[1]
        if isinstance(second, (int, float)) and not isinstance(second, bool):
            return [(float(first), float(second))]
    found: list[tuple[float, float]] = []
    for item in value:
        found.extend(_points(item))
    return found
