"""Resolve a US ZIP to county, CBSA, ZCTA, and state.

Contract
--------
``resolve_zip(zip_code) -> GeoContext``

Preserve leading zeros (text, width 5). The nationwide seed is
``data/seed/zip_crosswalk.csv``: Census ZCTA-to-county land share, the
July 2023 CBSA delineation (metropolitan division when one exists), and the
HRSA ZIP-to-ZCTA crosswalk for ZIP Codes that are not ZCTAs. ``94401``
through ``94404`` stay county ``06081``, division ``41884``, state ``CA``.

When several rows share a ZIP, the greatest ``tot_ratio`` wins. A tie breaks
toward the lower county FIPS.

:class:`InvalidZipError` means the value is not a 5-digit ZIP.
:class:`UnknownZipError` means it is a 5-digit ZIP absent from the seed.
This function does not open SQLite and does not use the network. The same
rows are cached in SQLite by :func:`dce.data.zip_seed.load_zip_seed`.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from dce.config import bundled_seed_dir
from dce.model.types import GeoContext

_SEED_NAME = "zip_crosswalk.csv"
_ZIP_WIDTH = 5
_ROW_CACHE: dict[str, tuple[int, list[dict[str, object]]]] = {}


class ZipResolutionError(Exception):
    """Base error for local ZIP resolution."""


class InvalidZipError(ZipResolutionError):
    """``zip_code`` is not a 5-digit US ZIP."""

    def __init__(self, zip_code: str) -> None:
        self.zip_code = zip_code.strip()
        super().__init__(f"ZIP must be 5 digits, got {zip_code.strip()!r}.")


class UnknownZipError(ZipResolutionError):
    """The ZIP is not in the bundled crosswalk seed."""

    def __init__(self, zip_code: str) -> None:
        self.zip_code = zip_code
        super().__init__(f"ZIP {zip_code} is not in the bundled ZIP crosswalk seed.")


class CrosswalkFixtureError(ZipResolutionError):
    """The committed HUD fixture is missing or malformed."""


def resolve_zip(zip_code: str) -> GeoContext:
    """Return geographies for one ZIP from the bundled crosswalk seed."""
    normalized = _normalize_zip(zip_code)
    matches = [row for row in _load_rows(_fixture_path()) if _text(row, "zip") == normalized]
    if not matches:
        raise UnknownZipError(normalized)
    chosen = min(matches, key=lambda row: (-_tot_ratio(row), _text(row, "county_fips")))
    return GeoContext(
        zip_code=normalized,
        zcta=_text(chosen, "zcta"),
        county_fips=_text(chosen, "county_fips"),
        cbsa=_text(chosen, "cbsa", allow_blank=True),
        state=_text(chosen, "state"),
    )


def _normalize_zip(zip_code: str) -> str:
    text = zip_code.strip()
    if len(text) != _ZIP_WIDTH or not text.isdigit():
        raise InvalidZipError(zip_code)
    return text


def _fixture_path() -> Path:
    path = bundled_seed_dir() / _SEED_NAME
    if path.is_file():
        return path
    # A frozen app keeps the seed under sys._MEIPASS even when the
    # development walk from this file cannot see pyproject.toml.
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str) and meipass:
        frozen = Path(meipass) / "data" / "seed" / _SEED_NAME
        if frozen.is_file():
            return frozen
    raise CrosswalkFixtureError(
        f"ZIP crosswalk seed {path.as_posix()} was not found. "
        "Run scripts/build_zip_inputs.py to regenerate data/seed/zip_crosswalk.csv."
    )


def _load_rows(path: Path) -> list[dict[str, object]]:
    try:
        stamp = path.stat().st_mtime_ns
    except FileNotFoundError as exc:
        raise CrosswalkFixtureError(f"ZIP crosswalk was not found: {path}") from exc
    cached = _ROW_CACHE.get(str(path))
    if cached is not None and cached[0] == stamp:
        return cached[1]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CrosswalkFixtureError(f"ZIP crosswalk was not found: {path}") from exc
    rows = _load_json(text, path) if path.suffix == ".json" else _load_csv(text, path)
    _ROW_CACHE[str(path)] = (stamp, rows)
    return rows


def _load_csv(text: str, path: Path) -> list[dict[str, object]]:
    try:
        reader = csv.DictReader(text.splitlines())
    except csv.Error as exc:
        raise CrosswalkFixtureError(f"ZIP crosswalk is not valid CSV: {path}") from exc
    if reader.fieldnames is None or "zip" not in reader.fieldnames:
        raise CrosswalkFixtureError(f"ZIP crosswalk {path} has no header.")
    parsed: list[dict[str, object]] = []
    for raw in reader:
        item: dict[str, object] = {
            str(key): (value or "") for key, value in raw.items() if key is not None
        }
        ratio = item.get("tot_ratio", "")
        if not isinstance(ratio, str) or ratio.strip() == "":
            raise CrosswalkFixtureError("tot_ratio must be a number.")
        try:
            item["tot_ratio"] = float(ratio)
        except ValueError as exc:
            raise CrosswalkFixtureError("tot_ratio must be a number.") from exc
        parsed.append(item)
    return parsed


def _load_json(text: str, path: Path) -> list[dict[str, object]]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CrosswalkFixtureError(f"HUD fixture is not valid JSON: {path}") from exc
    if not isinstance(raw, dict):
        raise CrosswalkFixtureError("HUD fixture must be a JSON object.")
    rows = raw.get("rows")
    if not isinstance(rows, list):
        raise CrosswalkFixtureError("HUD fixture must contain a rows list.")
    parsed: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise CrosswalkFixtureError("HUD fixture row must be an object.")
        parsed.append({str(key): value for key, value in row.items()})
    return parsed


def _text(row: dict[str, object], key: str, *, allow_blank: bool = False) -> str:
    value = row.get(key)
    if not isinstance(value, str) or (value == "" and not allow_blank):
        raise CrosswalkFixtureError(f"Crosswalk row is missing {key}.")
    return value


def _tot_ratio(row: dict[str, object]) -> float:
    value = row.get("tot_ratio", 0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CrosswalkFixtureError("tot_ratio must be a number.")
    return float(value)
