"""Local HUD ZIP resolution for the San Mateo demo slice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dce.geo.resolve import (
    CrosswalkFixtureError,
    InvalidZipError,
    UnknownZipError,
    resolve_zip,
)
from dce.model.types import GeoContext

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "hud_9440x.json"


def _row(zip_code: str) -> dict[str, object]:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert isinstance(rows, list)
    for row in rows:
        assert isinstance(row, dict)
        if row["zip"] == zip_code:
            return row
    raise AssertionError(f"{zip_code} missing from the committed fixture")


def test_resolve_94402_returns_county_and_fixture_cbsa() -> None:
    row = _row("94402")
    geo = resolve_zip("94402")
    assert geo == GeoContext(
        zip_code="94402",
        zcta=str(row["zcta"]),
        county_fips="06081",
        cbsa=str(row["cbsa"]),
        state=str(row["state"]),
    )
    assert geo.county_fips == "06081"
    assert geo.cbsa == "41884"
    assert geo.zcta == "94402"
    assert geo.state == "CA"
    assert isinstance(geo.county_fips, str)
    assert isinstance(geo.cbsa, str)


def test_resolve_strips_whitespace_and_covers_demo_zips() -> None:
    padded = resolve_zip("  94402  ")
    assert padded.zip_code == "94402"
    assert padded.county_fips == "06081"
    for zip_code in ("94401", "94402", "94403", "94404"):
        geo = resolve_zip(zip_code)
        row = _row(zip_code)
        assert geo.county_fips == "06081"
        assert geo.cbsa == row["cbsa"]
        assert geo.zcta == zip_code
        assert geo.state == "CA"


def test_unknown_zip_raises_typed_error() -> None:
    with pytest.raises(UnknownZipError) as exc_info:
        resolve_zip("99999")
    assert exc_info.value.zip_code == "99999"
    assert "99999" in str(exc_info.value)

    with pytest.raises(UnknownZipError) as leading_zero:
        resolve_zip("00501")
    assert leading_zero.value.zip_code == "00501"


def test_invalid_zip_raises_typed_error() -> None:
    with pytest.raises(InvalidZipError) as short:
        resolve_zip("9440")
    assert short.value.zip_code == "9440"
    with pytest.raises(InvalidZipError):
        resolve_zip("944021")
    with pytest.raises(InvalidZipError):
        resolve_zip("abcde")
    with pytest.raises(InvalidZipError):
        resolve_zip("")


def test_highest_address_ratio_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {
            "zip": "94402",
            "zcta": "94402",
            "county_fips": "06000",
            "cbsa": "99999",
            "state": "CA",
            "tot_ratio": 0.2,
        },
        {
            "zip": "94402",
            "zcta": "94402",
            "county_fips": "06081",
            "cbsa": "41884",
            "state": "CA",
            "tot_ratio": 0.8,
        },
    ]
    monkeypatch.setattr("dce.geo.resolve._load_rows", lambda _path: rows)
    geo = resolve_zip("94402")
    assert geo.county_fips == "06081"
    assert geo.cbsa == "41884"


def test_missing_fixture_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "dce.geo.resolve._fixture_path",
        lambda: tmp_path / "missing.json",
    )
    with pytest.raises(CrosswalkFixtureError, match="not found"):
        resolve_zip("94402")

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    monkeypatch.setattr("dce.geo.resolve._fixture_path", lambda: broken)
    with pytest.raises(CrosswalkFixtureError, match="not valid JSON"):
        resolve_zip("94402")


def test_fixture_search_failure_raises_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dce.geo.resolve._FIXTURE_PARTS",
        ("tests", "fixtures", "no-such-hud.json"),
    )
    with pytest.raises(CrosswalkFixtureError, match="no-such-hud.json"):
        resolve_zip("94402")
