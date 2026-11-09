"""DMV fuel-type aggregation. No network."""

from __future__ import annotations

import pytest

from dce.data.ingest import ca_ev
from dce.data.ingest.ca_ev import EvZipError, aggregate_ev_records, dmv_sql, fetch_ev_zip


def test_light_duty_fuels_map_to_bev_phev_fcev_and_total() -> None:
    records: list[dict[str, object]] = [
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Battery Electric",
            "Duty": "Light",
            "Vehicles": 2257,
        },
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Plug-in Hybrid",
            "Duty": "Light",
            "Vehicles": 561,
        },
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Hydrogen Fuel Cell",
            "Duty": "Light",
            "Vehicles": 4,
        },
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Gasoline",
            "Duty": "Light",
            "Vehicles": 10,
        },
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Gasoline",
            "Duty": "Heavy",
            "Vehicles": 999,
        },
    ]
    row = aggregate_ev_records("94402", records, source="dmv")
    assert row.state == "CA"
    assert row.source == "dmv"
    assert row.as_of == "2024-12-31"
    assert row.bev == 2257
    assert row.phev == 561
    assert row.fcev == 4
    assert row.total_ldv == 2257 + 561 + 4 + 10
    assert row.total_ldv != 2257 + 561 + 4 + 10 + 999


def test_sql_rejects_injection_and_fetch_stays_on_data_ca_gov(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(EvZipError, match="5 digits"):
        dmv_sql("94402' OR '1'='1")

    seen: list[str] = []

    def fake_json(url: str, **_kwargs: object) -> object:
        seen.append(url)
        return {
            "success": True,
            "result": {
                "records": [
                    {
                        "Date": "2024-12-31",
                        "ZIP Code": "94402",
                        "Fuel": "Battery Electric",
                        "Duty": "Light",
                        "Vehicles": 2257,
                    }
                ]
            },
        }

    monkeypatch.setattr(ca_ev, "request_json", fake_json)
    row = fetch_ev_zip("94402")
    assert row.bev == 2257
    assert row.total_ldv == 2257
    assert len(seen) == 1
    assert seen[0].startswith("https://data.ca.gov/api/3/action/datastore_search_sql?sql=")
    assert "94402" in seen[0]
    assert "b459d957-5d94-4b10-999d-770419870364" in seen[0]


def test_mixed_dates_raise() -> None:
    records: list[dict[str, object]] = [
        {
            "Date": "2024-12-31",
            "ZIP Code": "94402",
            "Fuel": "Gasoline",
            "Duty": "Light",
            "Vehicles": 1,
        },
        {
            "Date": "2023-12-31",
            "ZIP Code": "94402",
            "Fuel": "Gasoline",
            "Duty": "Light",
            "Vehicles": 1,
        },
    ]
    with pytest.raises(EvZipError, match="as_of"):
        aggregate_ev_records("94402", records, source="dmv")
