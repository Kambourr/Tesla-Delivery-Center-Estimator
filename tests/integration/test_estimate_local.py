"""Local inputs for a ZIP that is not the San Mateo demo.

Austin is a metropolitan OEWS area outside California. Greenfield, MA is
micropolitan, so the wage is the national SOC 49-3023 row. Amherst 01003 has
ACS population and rent but a suppressed median income.
"""

from __future__ import annotations

import pytest

from dce.orchestrator import estimate


def test_austin_78701_uses_its_own_wage_broker_rent_and_national_demand() -> None:
    result = estimate("78701")
    assert result.geo.state == "TX"
    assert result.geo.county_fips == "48453"
    assert result.geo.cbsa == "12420"
    assert result.dcf is not None and result.catchment is not None
    inputs = {row.name: row for row in result.provenance}
    wage = inputs["wage_annual"]
    rent = inputs["rent_psf_month"]
    deliveries = inputs["catchment_deliveries"]
    assert wage.value == pytest.approx(57440)
    assert wage.source == "bls_oews"
    assert wage.geography_level == "cbsa"
    assert wage.geography_id == "12420"
    assert wage.fallback is False
    assert rent.source == "broker_cbsa"
    assert rent.fallback is False
    assert rent.geography_level == "cbsa"
    assert rent.geography_id == "12420"
    assert rent.value == pytest.approx(15.09 / 12)
    assert deliveries.source == "cox_kbb_2025"
    assert deliveries.fallback is True
    assert deliveries.geography_level == "national"
    energy = inputs["energy_rate_kwh"]
    assert energy.fallback is False
    assert energy.source == "eia861"
    assert energy.geography_level == "utility"
    assert energy.geography_id == "1015"
    assert energy.value == pytest.approx(0.104451, abs=1e-6)
    tax = inputs["property_tax_rate"]
    assert tax.fallback is False
    assert tax.geography_level == "county"
    assert "Austin" in tax.detail
    assert result.estimated_annual_deliveries > 0
    assert result.cost_per_delivery > 0
    assert result.nearby_centers
    assert [driver.name for driver in result.drivers]


def test_greenfield_01301_uses_the_national_wage() -> None:
    result = estimate("01301")
    inputs = {row.name: row for row in result.provenance}
    wage = inputs["wage_annual"]
    assert result.geo.state == "MA"
    assert result.geo.cbsa == "24640"
    assert wage.value == pytest.approx(56420)
    assert wage.geography_level == "national"
    assert wage.geography_id == "00000"
    assert wage.fallback is True
    assert inputs["catchment_deliveries"].source == "cox_kbb_2025"
    assert result.estimated_annual_deliveries > 0


def test_amherst_01003_estimates_with_suppressed_income() -> None:
    result = estimate("01003")
    inputs = {row.name: row for row in result.provenance}
    income = inputs["median_hh_income"]
    assert income.value is None
    assert income.fallback is True
    assert income.source == "acs_2024_5yr"
    origin = inputs["zip_origin_deliveries"]
    assert origin.fallback is True
    assert "reference" in origin.detail
    assert result.estimated_annual_deliveries > 0
    assert inputs["population"].value == pytest.approx(13510)


def test_zip_without_its_own_rent_uses_a_marked_fallback() -> None:
    result = estimate("01093")
    rent = {row.name: row for row in result.provenance}["rent_psf_month"]
    assert rent.fallback is True
    assert rent.value is not None and rent.value > 0
    assert str(rent.source).startswith("acs_gross_rent")
    assert result.cost_per_delivery > 0
