"""Opt-in live calls to allowlisted hosts.

CI does not set ``DCE_NETWORK_TESTS``. Census is skipped unless
``CENSUS_API_KEY`` is present. BLS and data.ca.gov do not need a key.
"""

from __future__ import annotations

import os

import pytest

from dce.data.ingest.bls_oews import fetch_oews_wage
from dce.data.ingest.ca_ev import fetch_ev_zip
from dce.data.ingest.census_acs import fetch_zcta_acs

pytestmark = pytest.mark.skipif(
    os.environ.get("DCE_NETWORK_TESTS") != "1",
    reason="Set DCE_NETWORK_TESTS=1 to call allowlisted public hosts.",
)


def test_live_oews_and_dmv_for_94402() -> None:
    wage = fetch_oews_wage("41884", "49-3023")
    assert wage.area_code == "41860"
    assert wage.soc == "49-3023"
    assert wage.as_of.endswith("-05-01")
    assert wage.mean_annual is not None and wage.mean_annual > 10000
    assert wage.median_annual is not None and wage.median_annual > 10000

    ev = fetch_ev_zip("94402")
    assert ev.zip_code == "94402"
    assert ev.state == "CA"
    assert ev.source == "dmv"
    assert ev.bev is not None and ev.bev > 0
    assert ev.total_ldv is not None and ev.total_ldv >= ev.bev


@pytest.mark.skipif(not os.environ.get("CENSUS_API_KEY"), reason="CENSUS_API_KEY is not set.")
def test_live_census_acs_94402() -> None:
    row = fetch_zcta_acs("94402", year=2024)
    assert row.zcta == "94402"
    assert row.population is not None and row.population > 0
    assert row.median_hh_income is not None and row.median_hh_income > 0
