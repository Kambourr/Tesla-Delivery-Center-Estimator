"""Census ACS parsing and the allowlisted request. No network."""

from __future__ import annotations

import pytest

from dce.data.ingest import census_acs
from dce.data.ingest.census_acs import (
    CensusAcsError,
    CensusApiKeyError,
    fetch_zcta_acs,
    parse_census_table,
)


def _detailed_table() -> list[list[str]]:
    return [
        [
            "NAME",
            "B01003_001E",
            "B19013_001E",
            "B25046_001E",
            "B25077_001E",
            "zip code tabulation area",
        ],
        ["ZCTA5 94402", "25475", "172522", "18262", "2000001", "94402"],
    ]


def _subject_table() -> list[list[str]]:
    return [
        ["NAME", "S0801_C01_046E", "zip code tabulation area"],
        ["ZCTA5 94402", "26.2", "94402"],
    ]


def test_parse_keeps_population_income_and_treats_sentinels_as_missing() -> None:
    table = _detailed_table()
    table[1][2] = "-666666666"
    rows = parse_census_table(table, year=2024)
    assert len(rows) == 1
    row = rows[0]
    assert row.zcta == "94402"
    assert row.year == 2024
    assert row.population == 25475
    assert row.median_hh_income is None
    assert row.vehicles_available == 18262
    assert row.median_home_value == 2000001
    assert row.mean_commute is None


def test_fetch_builds_census_urls_and_does_not_store_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_json(url: str, **_kwargs: object) -> object:
        seen.append(url)
        if "/subject" in url:
            return _subject_table()
        return _detailed_table()

    monkeypatch.setattr(census_acs, "request_json", fake_json)
    row = fetch_zcta_acs("94402", year=2024, api_key="secret-key")
    assert row.population == 25475
    assert row.median_hh_income == 172522
    assert row.mean_commute == 26.2
    assert row.median_home_value == 2000001
    assert len(seen) == 2
    assert all(url.startswith("https://api.census.gov/data/2024/acs/acs5") for url in seen)
    assert all("key=secret-key" in url for url in seen)
    assert all("zip%20code%20tabulation%20area:94402" in url for url in seen)
    assert "secret-key" not in census_acs.census_dataset_url(2024)


def test_missing_key_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr("dce.config.load_local_env", lambda: None)

    def fail(url: str, **_kwargs: object) -> object:
        raise AssertionError(f"should not fetch {url}")

    monkeypatch.setattr(census_acs, "request_json", fail)
    with pytest.raises(CensusApiKeyError, match="CENSUS_API_KEY"):
        fetch_zcta_acs("94402", year=2024)


def test_bad_zcta_and_error_object_raise() -> None:
    with pytest.raises(CensusAcsError, match="5 digits"):
        fetch_zcta_acs("9440", year=2024, api_key="secret-key")
    with pytest.raises(CensusAcsError, match="unknown variable"):
        parse_census_table({"error": "unknown variable"}, year=2024)
