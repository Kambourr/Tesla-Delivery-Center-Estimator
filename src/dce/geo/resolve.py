"""Resolve a US ZIP to county, CBSA, ZCTA, and state.

Contract
--------
``resolve_zip(zip_code) -> GeoContext``

Preserve leading zeros (text, width 5). M1 reads the local HUD fixture
``tests/fixtures/hud_9440x.json`` for San Mateo demo ZIPs ``94401`` through
``94404``. County FIPS for those ZIPs is ``06081``. ``GeoContext.cbsa`` is
the CBSA code on the fixture row (the HUD ZIP–CBSA column). When several
rows share a ZIP, the greatest ``tot_ratio`` wins.

:class:`InvalidZipError` means the value is not a 5-digit ZIP.
:class:`UnknownZipError` means it is a 5-digit ZIP absent from the fixture.
Later milestones read rows the repository already stored. The HUD download
is :func:`dce.data.ingest.hud_crosswalk.fetch_zip_crosswalk`, not this
function. No network and no SQLite.
"""

from __future__ import annotations

import json
from pathlib import Path

from dce.model.types import GeoContext

_FIXTURE_PARTS = ("tests", "fixtures", "hud_9440x.json")
_ZIP_WIDTH = 5


class ZipResolutionError(Exception):
    """Base error for local ZIP resolution."""


class InvalidZipError(ZipResolutionError):
    """``zip_code`` is not a 5-digit US ZIP."""

    def __init__(self, zip_code: str) -> None:
        self.zip_code = zip_code.strip()
        super().__init__(f"ZIP must be 5 digits, got {zip_code.strip()!r}.")


class UnknownZipError(ZipResolutionError):
    """The ZIP is not in the local HUD crosswalk fixture."""

    def __init__(self, zip_code: str) -> None:
        self.zip_code = zip_code
        super().__init__(
            f"ZIP {zip_code} is not in the local HUD crosswalk fixture (M1 includes 94401-94404)."
        )


class CrosswalkFixtureError(ZipResolutionError):
    """The committed HUD fixture is missing or malformed."""


def resolve_zip(zip_code: str) -> GeoContext:
    """Return geographies for one ZIP from the local HUD fixture."""
    normalized = _normalize_zip(zip_code)
    matches = [row for row in _load_rows(_fixture_path()) if _text(row, "zip") == normalized]
    if not matches:
        raise UnknownZipError(normalized)
    chosen = max(matches, key=_tot_ratio)
    return GeoContext(
        zip_code=normalized,
        zcta=_text(chosen, "zcta"),
        county_fips=_text(chosen, "county_fips"),
        cbsa=_text(chosen, "cbsa"),
        state=_text(chosen, "state"),
    )


def _normalize_zip(zip_code: str) -> str:
    text = zip_code.strip()
    if len(text) != _ZIP_WIDTH or not text.isdigit():
        raise InvalidZipError(zip_code)
    return text


def _fixture_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent.joinpath(*_FIXTURE_PARTS)
        if candidate.is_file():
            return candidate
    relative = Path(*_FIXTURE_PARTS).as_posix()
    raise CrosswalkFixtureError(
        f"HUD crosswalk fixture {relative} was not found from the project directory."
    )


def _load_rows(path: Path) -> list[dict[str, object]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CrosswalkFixtureError(f"HUD fixture was not found: {path}") from exc
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


def _text(row: dict[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or value == "":
        raise CrosswalkFixtureError(f"HUD fixture row is missing {key}.")
    return value


def _tot_ratio(row: dict[str, object]) -> float:
    value = row.get("tot_ratio", 0)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CrosswalkFixtureError("tot_ratio must be a number.")
    return float(value)
