"""The 26 ZIPs that used to fail the nationwide precompute.

Each one had no origin deliveries of its own and no neighbor inside the
60-mile drive cap, so ``estimate`` raised:

    EstimateDataError: ZIP <zip> has no deliveries inside the 60-mile
    catchment, so cost per delivery is undefined.

The ZIPs were 00820, 00821, 00822, 00823, 00824, 00850, 00851 (St. Croix),
96799 (American Samoa), 96910, 96912, 96913, 96915, 96916, 96917, 96919,
96921, 96923, 96928, 96929, 96931, 96932 (Guam), 96950, 96951, 96952
(Northern Mariana Islands), 99635 and 99774 (remote Alaska). Territory
ZCTAs are absent from the ACS household file. The two Alaska ZCTAs publish
0 households. The isolated-origin rung gives them a positive volume without
changing any other ZIP.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dce.orchestrator import estimate
from dce.precompute import precompute

ISOLATED_ZIPS = (
    "00820",
    "00821",
    "00822",
    "00823",
    "00824",
    "00850",
    "00851",
    "96799",
    "96910",
    "96912",
    "96913",
    "96915",
    "96916",
    "96917",
    "96919",
    "96921",
    "96923",
    "96928",
    "96929",
    "96931",
    "96932",
    "96950",
    "96951",
    "96952",
    "99635",
    "99774",
)


def test_isolated_zips_estimate_and_store(tmp_path: Path) -> None:
    assert len(ISOLATED_ZIPS) == 26
    for code in ISOLATED_ZIPS:
        result = estimate(code)
        assert result.estimated_annual_deliveries > 0
        origin = next(row for row in result.provenance if row.name == "zip_origin_deliveries")
        assert origin.fallback is True
        assert "Isolated ZIP fallback" in origin.detail
    report = precompute(data_dir=tmp_path, zip_codes=ISOLATED_ZIPS, workers=1)
    assert report.requested == 26
    assert report.computed == 26
    assert report.errors == 0


def test_a_served_zip_does_not_use_the_isolated_rung() -> None:
    result = estimate("94402")
    origin = next(row for row in result.provenance if row.name == "zip_origin_deliveries")
    assert "Isolated ZIP fallback" not in origin.detail


# Goldens on 2026.11.9-compact-results: broker rents, commercial tax on real
# property, and the DoD construction factor apply on top of the isolated
# origin. A territory ZCTA has no ACS households, so the proxy is one
# household. The two Alaska ZCTAs take the DoD county factor (2.97 and 3.17).
# (deliveries per year, cost per delivery, standalone NPV)
ISOLATED_GOLDEN = {
    "96799": (0.003947761649340268, 427259571.3274323, -8616327.816918382),
    "99635": (0.15261197391415274, 14951451.000060724, -13159469.22533848),
    "99774": (0.003947761649340268, 591444901.5406477, -13586509.499917928),
}


def test_isolated_zip_goldens() -> None:
    for code, (deliveries, per_delivery, npv) in ISOLATED_GOLDEN.items():
        result = estimate(code)
        assert result.estimated_annual_deliveries == pytest.approx(deliveries, rel=1e-9)
        assert result.cost_per_delivery == pytest.approx(per_delivery, rel=1e-9)
        assert result.dcf.standalone.npv == pytest.approx(npv, abs=1.0)
