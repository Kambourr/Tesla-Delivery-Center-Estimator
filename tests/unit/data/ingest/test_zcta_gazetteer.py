"""Census ZCTA gazetteer parsing. No network."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from dce.data.ingest.zcta_gazetteer import (
    GazetteerError,
    gazetteer_url,
    parse_gazetteer_zip,
    parse_zcta_gazetteer,
)

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "geo" / "gazetteer_2024_sample.txt"


def test_sample_gazetteer_has_the_94402_internal_point() -> None:
    rows = parse_zcta_gazetteer(_FIXTURE.read_text(encoding="utf-8"), year=2024)
    by_zcta = {row.zcta: row for row in rows}
    point = by_zcta["94402"]
    assert point.lat == pytest.approx(37.540103)
    assert point.lon == pytest.approx(-122.330103)
    assert point.vintage == "2024"
    assert point.as_of == "2024-01-01"
    assert "94014" in by_zcta


def test_zip_download_uses_the_census_gazetteer_url_and_parses() -> None:
    assert gazetteer_url(2024).startswith("https://www2.census.gov/")
    text = _FIXTURE.read_text(encoding="utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("2024_Gaz_zcta_national.txt", text)
    rows = parse_gazetteer_zip(buffer.getvalue(), year=2024)
    assert rows[0].zcta == "94402"
    with pytest.raises(GazetteerError, match="not a ZIP"):
        parse_gazetteer_zip(b"not a zip", year=2024)
