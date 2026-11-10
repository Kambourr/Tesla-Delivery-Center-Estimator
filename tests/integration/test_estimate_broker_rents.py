"""Goldens for broker market rents (model version 2026.11.7-broker-rents).

Rent is the only input this change moves. Deliveries, wage, electricity,
property tax, and the fit-out index come from the same seed as before.

| ZIP | Rent rung | Before ($/SF/mo, $/delivery, NPV) | After |
|---|---|---|---|
| 10001 | broker_county 36061, C&W Manhattan office, full-service gross / 1.15 | 3.361 ACS, $513, +$20.57M | 5.389, $606, +$17.30M |
| 94402 | cbsa_raw 41884, Kidder Mathews Peninsula industrial | 2.14, $611, +$11.07M | unchanged |
| 78701 | broker_cbsa 12420, C&W Austin office service/flex | 2.759 ACS, $921, +$1.22M | 1.2575, $698, +$3.64M |
| 33139 | broker_cbsa 33124, C&W Miami-Dade office service | 1.822 ACS, $867, +$1.48M | 1.6742, $843, +$1.71M |
| 82401 | acs_gross_rent, Worland WY has no CBSA and no broker row | 0.721, $46,485, -$7.48M | unchanged |
"""

from __future__ import annotations

import pytest

from dce.orchestrator import estimate
from dce.precompute.version import MODEL_VERSION

# zip: (rent $/SF/month, source, level, id, fallback, deliveries, $/delivery, NPV, drivers)
GOLDEN = {
    "10001": (
        74.37 / 1.15 / 12,
        "broker_county",
        "county",
        "36061",
        False,
        8190.38,
        605.59,
        17_301_653.0,
        ("labor", "lease", "capex"),
    ),
    "94402": (
        2.14,
        "cbsa_raw",
        "cbsa",
        "41884",
        False,
        5565.19,
        611.28,
        11_069_085.0,
        ("labor", "lease", "capex"),
    ),
    "78701": (
        15.09 / 12,
        "broker_cbsa",
        "cbsa",
        "12420",
        False,
        2512.20,
        697.98,
        3_636_252.0,
        ("labor", "lease", "capex"),
    ),
    "33139": (
        20.09 / 12,
        "broker_cbsa",
        "cbsa",
        "33124",
        False,
        2272.49,
        843.07,
        1_713_836.0,
        ("labor", "lease", "capex"),
    ),
    "82401": (
        0.721,
        "acs_gross_rent",
        "zcta",
        "82401",
        True,
        31.61,
        46_484.54,
        -7_477_759.0,
        ("labor", "capex", "lease"),
    ),
}


def test_model_version_is_the_broker_rent_stamp() -> None:
    assert MODEL_VERSION == "2026.11.7-broker-rents"


@pytest.mark.parametrize("zip_code", sorted(GOLDEN))
def test_broker_rent_goldens(zip_code: str) -> None:
    rent, source, level, geo_id, fallback, deliveries, per_delivery, npv, drivers = GOLDEN[zip_code]
    result = estimate(zip_code)
    inputs = {row.name: row for row in result.provenance}
    resolved = inputs["rent_psf_month"]
    assert resolved.value == pytest.approx(rent, abs=1e-4)
    assert resolved.source == source
    assert resolved.geography_level == level
    assert resolved.geography_id == geo_id
    assert resolved.fallback is fallback
    assert result.estimated_annual_deliveries == pytest.approx(deliveries, abs=0.01)
    assert result.cost_per_delivery == pytest.approx(per_delivery, abs=0.01)
    assert result.dcf is not None
    assert result.dcf.standalone.npv == pytest.approx(npv, abs=1.0)
    assert tuple(driver.name for driver in result.drivers) == drivers


def test_manhattan_now_pays_more_rent_per_delivery_than_before() -> None:
    result = estimate("10001")
    inputs = {row.name: row for row in result.provenance}
    detail = inputs["rent_psf_month"].detail
    assert "MarketBeat Manhattan Office Q3 2026" in detail
    assert "office_showroom_proxy" in detail
    assert "Confidence medium" in detail
    # The ACS residential proxy priced this ZIP at $3.361 per square foot per month.
    assert inputs["rent_psf_month"].value is not None
    assert inputs["rent_psf_month"].value > 3.361 * 1.5
    assert result.components["lease"] > 1_800_000
