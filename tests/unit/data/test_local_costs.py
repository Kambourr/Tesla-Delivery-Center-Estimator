"""Local electricity, tax, and price-index ladders. Seeds only."""

from __future__ import annotations

import pytest
import yaml

from dce.config import assumptions_path
from dce.data.electricity import resolve_electricity
from dce.data.local_costs import resolve_local_prices
from dce.data.price_index import resolve_price_index
from dce.data.property_tax import resolve_property_tax
from dce.geo.resolve import resolve_zip
from dce.model.assumptions import parse_assumptions
from dce.model.costs import build_cost_inputs, nnn_opex_load, upfront_capex
from dce.precompute.version import MODEL_VERSION


def _assumptions():
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return parse_assumptions(raw)


def test_model_version_is_the_local_cost_stamp() -> None:
    assert MODEL_VERSION == "2026.11.7-broker-rents"


def test_94402_keeps_pge_b10() -> None:
    geo = resolve_zip("94402")
    power = resolve_electricity(geo)
    assert power.tier == "utility_tariff"
    assert power.utility_id == "14328"
    assert power.schedule == "B-10"
    assert power.energy_rate_kwh == pytest.approx(0.2875)
    assert power.demand_rate_kw == pytest.approx(20.50)
    assert power.demand_embedded is False
    assert power.source == "pge_pdf"


def test_austin_miami_manhattan_and_worland_are_not_pge() -> None:
    expected = {
        "78701": ("1015", "utility_average", 0.104451),
        "33139": ("6452", "utility_average", 0.107455),
        "10001": ("4226", "utility_average", 0.158833),
        "82401": ("14354", "utility_average", 0.098052),
    }
    for zip_code, (utility, tier, energy) in expected.items():
        power = resolve_electricity(resolve_zip(zip_code))
        assert power.utility_id == utility
        assert power.tier == tier
        assert power.energy_rate_kwh == pytest.approx(energy, abs=1e-6)
        assert power.demand_rate_kw == 0.0
        assert power.demand_embedded is True
        assert power.source == "eia861"
        assert "Pacific Gas" not in power.utility_name


def test_property_tax_ladder_uses_studied_places() -> None:
    mateo = resolve_property_tax(resolve_zip("94402"))
    assert mateo.tier == "state_urban"
    assert mateo.place == "Los Angeles"
    assert mateo.effective_rate == pytest.approx(0.01200)

    austin = resolve_property_tax(resolve_zip("78701"))
    assert austin.tier == "county"
    assert austin.place == "Austin"
    assert austin.effective_rate == pytest.approx(0.01808)

    miami = resolve_property_tax(resolve_zip("33139"))
    assert miami.tier == "county"
    assert miami.effective_rate == pytest.approx(0.01803)

    manhattan = resolve_property_tax(resolve_zip("10001"))
    assert manhattan.tier == "county"
    assert manhattan.effective_rate == pytest.approx(0.01418)

    worland = resolve_property_tax(resolve_zip("82401"))
    assert worland.tier == "county"
    assert worland.place == "Worland"
    assert worland.effective_rate == pytest.approx(0.00743)


def test_fitout_index_is_goods_rpp_over_us_goods() -> None:
    bay = resolve_price_index(resolve_zip("94402"))
    assert bay.tier == "metro"
    assert bay.geography_id == "41860"
    assert bay.fitout_index == pytest.approx(108.465 / 99.567)

    austin = resolve_price_index(resolve_zip("78701"))
    assert austin.geography_id == "12420"
    assert austin.fitout_index == pytest.approx(93.757 / 99.567)
    assert austin.fitout_index < 1.0

    rural = resolve_price_index(resolve_zip("82401"))
    assert rural.tier == "state"
    assert rural.geography_id == "WY"


def test_same_zip_resolves_twice_to_the_same_inputs() -> None:
    assumptions = _assumptions()
    geo = resolve_zip("78701")
    assert resolve_local_prices(geo, assumptions, 2.759) == resolve_local_prices(
        geo, assumptions, 2.759
    )


def test_nnn_load_is_unchanged_at_the_reference_rate() -> None:
    assert nnn_opex_load(
        0.15,
        reference_rate=0.011,
        local_rate=0.011,
        assessed_value_psf=250.0,
        rent_psf_year=2.14 * 12,
    ) == pytest.approx(0.15)
    higher = nnn_opex_load(
        0.15,
        reference_rate=0.011,
        local_rate=0.01808,
        assessed_value_psf=250.0,
        rent_psf_year=25.0,
    )
    assert higher == pytest.approx(0.15 + 250.0 * (0.01808 - 0.011) / 25.0)
    assert nnn_opex_load(
        0.15,
        reference_rate=0.011,
        local_rate=0.02,
        assessed_value_psf=250.0,
        rent_psf_year=0.0,
    ) == pytest.approx(0.15)


def test_fitout_index_of_one_keeps_national_capex() -> None:
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    plain = upfront_capex(raw)
    indexed = upfront_capex(raw, fitout_index=1.0)
    assert indexed == plain
    costs = build_cost_inputs(
        raw,
        rent_psf_month=2.14,
        wage_annual=50_000.0,
        energy_rate_kwh=0.2,
        demand_rate_kw=10.0,
        annual_deliveries=4500.0,
    )
    shifted = build_cost_inputs(
        raw,
        rent_psf_month=2.14,
        wage_annual=50_000.0,
        energy_rate_kwh=0.2,
        demand_rate_kw=10.0,
        annual_deliveries=4500.0,
        fitout_index=1.0,
    )
    assert shifted == costs
