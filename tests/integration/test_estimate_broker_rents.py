"""Goldens for broker market rents on 2026.11.8-broker-rents-commercial-tax-acf.

Broker rents (#18) and the commercial tax class plus DoD construction cost
factor apply together. Deliveries and wage come from the same seed as main.
"Before" is main (2026.11.7-broker-rents, BEA goods fit-out, fixtures-exempt
tax not grossed up). "After" is this model.

| ZIP | Rent rung | Before ($/delivery, NPV) | After ($/delivery, NPV) |
|---|---|---|---|
| 10001 | broker_county 36061, C&W Manhattan office, full-service gross / 1.15 | $605.59, +$17.30M | $615.71, +$16.73M |
| 94402 | cbsa_raw 41884, Kidder Mathews Peninsula industrial | $611.28, +$11.07M | $618.51, +$10.75M |
| 78701 | broker_cbsa 12420, C&W Austin office service/flex | $697.98, +$3.64M | $683.46, +$3.92M |
| 33139 | broker_cbsa 33124, C&W Miami-Dade office service | $843.07, +$1.71M | $820.62, +$2.10M |
| 82401 | acs_gross_rent, Worland WY has no CBSA and no broker row | $46,484.54, -$7.48M | $47,359.39, -$7.69M |
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
        615.71,
        16_730_465.0,
        ("labor", "lease", "capex"),
    ),
    "94402": (
        2.14,
        "cbsa_raw",
        "cbsa",
        "41884",
        False,
        5565.19,
        618.51,
        10_754_365.0,
        ("labor", "lease", "capex"),
    ),
    "78701": (
        15.09 / 12,
        "broker_cbsa",
        "cbsa",
        "12420",
        False,
        2512.20,
        683.46,
        3_915_798.0,
        ("labor", "lease", "capex"),
    ),
    "33139": (
        20.09 / 12,
        "broker_cbsa",
        "cbsa",
        "33124",
        False,
        2272.49,
        820.62,
        2_104_644.0,
        ("labor", "lease", "capex"),
    ),
    "82401": (
        0.721,
        "acs_gross_rent",
        "zcta",
        "82401",
        True,
        31.61,
        47_359.39,
        -7_689_572.0,
        ("labor", "capex", "lease"),
    ),
}


def test_model_version_is_the_combined_stamp() -> None:
    assert MODEL_VERSION == "2026.11.8-broker-rents-commercial-tax-acf"


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
