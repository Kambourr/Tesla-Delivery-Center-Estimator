"""OEWS series ids, the 41884 → 41860 join, and payload parsing. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dce.data.ingest import bls_oews
from dce.data.ingest.bls_oews import (
    OEWS_SOC_AUTO_TECH,
    SF_OAKLAND_CBSA,
    OewsError,
    fetch_oews_wage,
    oews_area_for_cbsa,
    oews_series_id,
    parse_oews_payload,
)

_DEMO = Path(__file__).resolve().parents[4] / "data" / "demo" / "san_mateo" / "oews_may_2025.json"


def test_series_ids_match_the_may_2025_public_api() -> None:
    assert oews_series_id("41860", "49-3023", "04") == "OEUM004186000000049302304"
    assert oews_series_id("0041860", "493023", "13") == "OEUM004186000000049302313"
    assert len(oews_series_id(SF_OAKLAND_CBSA, OEWS_SOC_AUTO_TECH, "04")) == 25


def test_hud_division_maps_to_the_parent_oews_metro() -> None:
    assert oews_area_for_cbsa("41884") == "41860"
    assert oews_area_for_cbsa("41860") == "41860"
    assert oews_area_for_cbsa("  41884  ") == "41860"
    with pytest.raises(OewsError, match="5-digit"):
        oews_area_for_cbsa("4188")


def test_parse_may_2025_fixture_wages() -> None:
    payload = json.loads(_DEMO.read_text(encoding="utf-8"))
    wage = parse_oews_payload(
        payload["payload"],
        area_code=payload["area_code"],
        area_name=payload["area_name"],
        soc=payload["soc"],
        soc_title=payload["soc_title"],
        mean_series_id=payload["mean_series_id"],
        median_series_id=payload["median_series_id"],
    )
    assert wage.area_code == "41860"
    assert wage.area_name == "San Francisco-Oakland-Fremont, CA"
    assert wage.soc == "49-3023"
    assert wage.soc_title == "Automotive Service Technicians and Mechanics"
    assert wage.mean_annual == 75730
    assert wage.median_annual == 76030
    assert wage.as_of == "2025-05-01"


def test_fetch_posts_the_mapped_series_and_keeps_the_key_out_of_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_json(url: str, **kwargs: object) -> object:
        captured["url"] = url
        captured["body"] = kwargs.get("body")
        fixture = json.loads(_DEMO.read_text(encoding="utf-8"))
        return fixture["payload"]

    monkeypatch.setattr(bls_oews, "request_json", fake_json)
    monkeypatch.setattr(bls_oews, "read_api_key", lambda _name: "bls-secret")
    wage = fetch_oews_wage("41884", "49-3023", end_year=2026)
    assert wage.area_code == "41860"
    assert wage.mean_annual == 75730
    assert captured["url"] == "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    body = captured["body"]
    assert isinstance(body, bytes)
    posted = json.loads(body.decode("utf-8"))
    assert posted["registrationkey"] == "bls-secret"
    assert "OEUM004186000000049302304" in posted["seriesid"]
    assert "OEUM004186000000049302313" in posted["seriesid"]
    assert "bls-secret" not in str(captured["url"])


def test_national_series_and_bulk_csv_and_division_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dce.data.ingest.bls_oews import (
        HUD_DIVISION_TO_OEWS_CBSA,
        OEWS_NATIONAL_AREA,
        fetch_oews_area_wages,
        oews_national_series_id,
        parse_oews_bulk_csv,
    )

    assert oews_national_series_id("49-3023", "04") == "OEUN000000000000049302304"
    assert len(oews_national_series_id("49-3023", "13")) == 25
    assert HUD_DIVISION_TO_OEWS_CBSA["35614"] == "35620"
    assert len(HUD_DIVISION_TO_OEWS_CBSA) == 37
    text = (
        "AREA,AREA_TITLE,OCC_CODE,OCC_TITLE,A_MEAN,A_MEDIAN,NAICS,O_GROUP\n"
        "0000000,United States,49-3023,Automotive Service Technicians and Mechanics,"
        "56420,50620,000000,detailed\n"
        "0041860,San Francisco-Oakland-Fremont CA,49-3023,Automotive,75730,*,000000,detailed\n"
        "0041860,San Francisco-Oakland-Fremont CA,49-3023,Automotive,1,1,441100,detailed\n"
    )
    rows = {row.area_code: row for row in parse_oews_bulk_csv(text, year=2025)}
    assert rows[OEWS_NATIONAL_AREA].mean_annual == 56420
    assert rows[OEWS_NATIONAL_AREA].median_annual == 50620
    assert rows["41860"].mean_annual == 75730
    assert rows["41860"].median_annual is None

    def fake_json(url: str, **_kwargs: object) -> object:
        assert url.startswith("https://api.bls.gov/")
        return {
            "status": "REQUEST_SUCCEEDED",
            "Results": {
                "series": [
                    {
                        "seriesID": "OEUN000000000000049302304",
                        "data": [{"year": "2025", "period": "A01", "value": "56420"}],
                    }
                ]
            },
        }

    monkeypatch.setattr(bls_oews, "request_json", fake_json)
    monkeypatch.setattr(bls_oews, "read_api_key", lambda _name: None)
    wages = fetch_oews_area_wages(
        (),
        (("49-3023", "Automotive Service Technicians and Mechanics"),),
        datatypes=("04",),
        national=True,
        end_year=2025,
    )
    assert wages[0].area_code == OEWS_NATIONAL_AREA
    assert wages[0].mean_annual == 56420
    assert wages[0].median_annual is None


def test_failed_status_raises() -> None:
    with pytest.raises(OewsError, match="REQUEST_FAILED"):
        parse_oews_payload(
            {"status": "REQUEST_FAILED", "message": ["bad series"]},
            area_code="41860",
            area_name="San Francisco-Oakland-Fremont, CA",
            soc="49-3023",
            soc_title="Automotive Service Technicians and Mechanics",
            mean_series_id="OEUM004186000000049302304",
            median_series_id="OEUM004186000000049302313",
        )
