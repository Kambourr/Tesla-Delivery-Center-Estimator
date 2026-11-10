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


def test_manhattan_10001_uses_commercial_tax_and_the_dod_construction_factor() -> None:
    """Golden for 10001 on 2026.11.8-broker-rents-commercial-tax-acf.

    Rent is the Manhattan broker row (county 36061), not the ACS fallback.
    """
    result = estimate("10001")
    inputs = {row.name: row for row in result.provenance}
    tax = inputs["property_tax_rate"]
    assert tax.value == pytest.approx(0.017014)
    assert tax.source == "lincoln_mcfe_2024"
    assert tax.geography_level == "county"
    assert tax.geography_id == "36061"
    assert tax.fallback is False
    assert "Commercial class" in tax.detail
    assert "not the homestead rate" in tax.detail
    fitout = inputs["fitout_index"]
    assert fitout.value == pytest.approx(1.32)
    assert fitout.source == "dod_ufs_3_701_01_2026"
    assert fitout.geography_id == "36061"
    assert fitout.fallback is False
    assert inputs["opex_load"].value == pytest.approx(0.17324895, abs=1e-7)
    assert result.estimated_annual_deliveries == pytest.approx(8190.4, abs=0.5)
    assert result.cost_per_delivery == pytest.approx(615.71, abs=0.01)
    assert [driver.name for driver in result.drivers] == ["labor", "lease", "capex"]
    assert result.components["capex"] == pytest.approx(474_000.0, abs=1.0)
    assert result.dcf is not None
    assert result.dcf.standalone.npv == pytest.approx(16.73e6, abs=0.01e6)
    # Year-0 capex is fit-out x 1.32 plus equipment.
    assert result.dcf.standalone.years[0].capex == pytest.approx(
        100.0 * 1.32 * 25_000.0 * 1.20 + 780_000.0, abs=1
    )


def test_golden_cost_per_delivery_for_the_five_report_zips() -> None:
    expected = {
        "10001": (615.71, 16.73e6),
        "94402": (618.51, 10.75e6),
        "78701": (683.46, 3.92e6),
        "33139": (820.62, 2.10e6),
        "82401": (47359.39, -7.69e6),
    }
    for zip_code, (cost, npv) in expected.items():
        result = estimate(zip_code)
        assert result.cost_per_delivery == pytest.approx(cost, abs=0.01), zip_code
        assert result.dcf is not None
        assert result.dcf.standalone.npv == pytest.approx(npv, abs=0.01e6), zip_code
