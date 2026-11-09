"""Fixture load of ACS, OEWS, and DMV for San Mateo. No API keys and no network."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from dce.data.demo_seed import load_san_mateo_demo, refresh_san_mateo
from dce.data.ingest.bls_oews import OewsWage
from dce.data.ingest.ca_ev import EvZipCount
from dce.data.ingest.census_acs import CensusApiKeyError, ZctaAcs
from dce.data.registry import staleness_status
from dce.storage.connection import get_connection
from dce.storage.repository import get_ev_zip, get_oews_wage, get_source, get_zcta_acs

_ROOT = Path(__file__).resolve().parents[3]
_FETCHED_AT = "2026-11-09T12:00:00Z"
_TODAY = date(2026, 11, 9)


def test_fixture_load_94402_acs_oews_and_dmv_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(url: str, **_kwargs: object) -> bytes:
        raise AssertionError(f"fixture load must not fetch {url}")

    monkeypatch.setattr("dce.data.ingest.http.request_bytes", fail)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    conn = get_connection(tmp_path)
    try:
        first = load_san_mateo_demo(conn, fetched_at=_FETCHED_AT)
        second = load_san_mateo_demo(conn, fetched_at=_FETCHED_AT)
        assert first == second
        assert first.acs_rows == 4
        assert first.oews_rows == 1
        assert first.ev_rows == 4

        acs = get_zcta_acs(conn, "94402", 2024)
        assert acs is not None
        assert acs.population == 25475
        assert acs.median_hh_income == 172522
        assert acs.vehicles_available == 18262
        assert acs.mean_commute == 26.2
        assert acs.median_home_value == 2000001

        wage = get_oews_wage(conn, "41860", "49-3023", "2025-05-01")
        assert wage is not None
        assert wage.area_name == "San Francisco-Oakland-Fremont, CA"
        assert wage.soc == "49-3023"
        assert wage.soc_title == "Automotive Service Technicians and Mechanics"
        assert wage.mean_annual == 75730
        assert wage.median_annual == 76030

        ev = get_ev_zip(conn, "94402", "2024-12-31", "dmv")
        assert ev is not None
        assert ev.state == "CA"
        assert ev.bev == 2257
        assert ev.phev == 561
        assert ev.fcev == 4
        assert ev.total_ldv == 2257 + 248 + 411 + 16136 + 1784 + 4 + 2 + 561

        census = get_source(conn, "census_acs")
        oews = get_source(conn, "bls_oews")
        dmv = get_source(conn, "ca_ev_dmv")
        assert census is not None and census.as_of == "2024-12-31"
        assert oews is not None and oews.as_of == "2025-05-01"
        assert dmv is not None and dmv.as_of == "2024-12-31"
        assert "key=" not in census.url
        assert census.ttl_days == 548
        for record in (census, oews, dmv):
            assert record.as_of is not None
            assert (
                staleness_status(date.fromisoformat(record.as_of), record.ttl_days, _TODAY)
                == "stale"
            )
    finally:
        conn.close()


def test_demo_script_exits_zero_without_keys(tmp_path: Path) -> None:
    database = tmp_path / "dce.sqlite"
    env = os.environ.copy()
    env.pop("CENSUS_API_KEY", None)
    env.pop("BLS_API_KEY", None)
    completed = subprocess.run(
        [sys.executable, "scripts/fetch_demo_cache.py", "--db", str(database)],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "4 ACS rows" in completed.stdout
    report = subprocess.run(
        [
            sys.executable,
            "scripts/check_staleness.py",
            "--db",
            str(database),
            "--today",
            "2026-11-09",
        ],
        cwd=_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert report.returncode == 0, report.stderr
    assert "census_acs\t2024-12-31\tstale" in report.stdout
    assert "bls_oews\t2025-05-01\tstale" in report.stdout
    assert "ca_ev_dmv\t2024-12-31\tstale" in report.stdout
    conn = get_connection(tmp_path)
    try:
        acs = get_zcta_acs(conn, "94402", 2024)
        assert acs is not None
        assert acs.population == 25475
        assert acs.median_hh_income == 172522
    finally:
        conn.close()


def test_refresh_maps_hud_division_and_refuses_to_start_without_a_census_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.setattr("dce.config.load_local_env", lambda: None)
    conn = get_connection(tmp_path)
    try:
        with pytest.raises(CensusApiKeyError, match="CENSUS_API_KEY"):
            refresh_san_mateo(conn, fetched_at=_FETCHED_AT)
        assert get_zcta_acs(conn, "94402", 2024) is None
    finally:
        conn.close()

    seen: dict[str, str] = {}

    def fake_acs(zcta: str, *, year: int, api_key: str | None = None) -> ZctaAcs:
        del api_key
        assert year == 2024
        return ZctaAcs(zcta, year, 1.0, 2.0, 3.0, 4.0, 5.0)

    def fake_wage(area_code: str, soc: str, **_kwargs: object) -> OewsWage:
        seen["area"] = area_code
        seen["soc"] = soc
        return OewsWage(
            area_code=area_code,
            area_name="San Francisco-Oakland-Fremont, CA",
            soc=soc,
            soc_title="Automotive Service Technicians and Mechanics",
            mean_annual=75730.0,
            median_annual=76030.0,
            as_of="2025-05-01",
        )

    def fake_ev(zip_code: str) -> EvZipCount:
        return EvZipCount(zip_code, "CA", 1.0, 0.0, 0.0, 1.0, "2024-12-31", "dmv")

    monkeypatch.setenv("CENSUS_API_KEY", "not-a-real-key")
    monkeypatch.setattr("dce.data.demo_seed.fetch_zcta_acs", fake_acs)
    monkeypatch.setattr("dce.data.demo_seed.fetch_oews_wage", fake_wage)
    monkeypatch.setattr("dce.data.demo_seed.fetch_ev_zip", fake_ev)
    conn = get_connection(tmp_path)
    try:
        counts = refresh_san_mateo(conn, fetched_at=_FETCHED_AT)
        assert counts.acs_rows == 4
        assert seen == {"area": "41860", "soc": "49-3023"}
        stored = get_oews_wage(conn, "41860", "49-3023", "2025-05-01")
        assert stored is not None
        assert stored.mean_annual == 75730
        census = get_source(conn, "census_acs")
        assert census is not None
        assert "not-a-real-key" not in census.url
    finally:
        conn.close()
