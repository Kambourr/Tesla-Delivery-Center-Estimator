"""Local electricity, tax, and price-index ladders. Seeds only."""

from __future__ import annotations

import pytest
import yaml

from dce.config import assumptions_path
from dce.data.construction_cost import resolve_construction_cost
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


def test_model_version_is_the_compact_results_stamp() -> None:
    assert MODEL_VERSION == "2026.11.9-compact-results"


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
    # San Mateo County is not studied. It shares metro division 41884 with
    # San Francisco, so it borrows San Francisco, not Los Angeles.
    mateo = resolve_property_tax(resolve_zip("94402"))
    assert mateo.tier == "cbsa"
    assert mateo.cbsa == "41884"
    assert mateo.place == "San Francisco"
    assert mateo.effective_rate == pytest.approx(0.01171)
    assert mateo.fixtures_exempt is False

    austin = resolve_property_tax(resolve_zip("78701"))
    assert austin.tier == "county"
    assert austin.place == "Austin"
    assert austin.effective_rate == pytest.approx(0.01808)
    assert austin.source_table == "3b;4c"

    miami = resolve_property_tax(resolve_zip("33139"))
    assert miami.tier == "county"
    assert miami.effective_rate == pytest.approx(0.01803)

    worland = resolve_property_tax(resolve_zip("82401"))
    assert worland.tier == "county"
    assert worland.place == "Worland"
    assert worland.effective_rate == pytest.approx(0.00743)
    assert worland.source_table == "3c;4e"


def test_manhattan_is_the_commercial_class_on_real_property() -> None:
    # Lincoln 2024 Table 3a, New York City, $1 million commercial: 1.418% of
    # $1.2 million, bill $17,014. Homestead is 1.249% (Table 2a). New York
    # exempts fixtures (Table 4g), so the bill is all on the $1 million of
    # land and building: 1.7014%.
    tax = resolve_property_tax(resolve_zip("10001"))
    assert tax.tier == "county"
    assert tax.place == "New York City"
    assert tax.commercial_rate == pytest.approx(0.01418)
    assert tax.commercial_rate != pytest.approx(0.01249)
    assert tax.fixtures_exempt is True
    assert tax.effective_rate == pytest.approx(17_014 / 1_000_000)
    assert tax.industrial_rate == pytest.approx(0.00532)
    assert tax.source_table == "3a;4a"


def test_new_york_city_and_chicago_do_not_stand_in_for_neighbours() -> None:
    # Westchester shares division 35614 with Manhattan; Nassau shares the
    # parent CBSA. Neither borrows New York City.
    for zip_code in ("10601", "11501"):
        tax = resolve_property_tax(resolve_zip(zip_code))
        assert tax.place == "Buffalo"
        assert tax.tier == "state_urban"
    # Bergen County, NJ is in the Newark division, so it borrows Newark.
    hackensack = resolve_property_tax(resolve_zip("07601"))
    assert hackensack.tier == "cbsa"
    assert hackensack.place == "Newark"


def test_every_seed_rate_is_a_commercial_table_row() -> None:
    from dce.data.seed_csv import read_seed_csv

    rows = list(read_seed_csv("property_tax_commercial.csv"))
    assert rows
    for row in rows:
        tables = row["source_table"].split(";")
        assert tables[0] in {"3a", "3b", "3c"}
        assert tables[1] in {"4a", "4c", "4e"}
        effective = float(row["effective_rate"])
        published = float(row["commercial_rate"])
        if row["fixtures_exempt"] == "true":
            assert effective == pytest.approx(int(row["commercial_tax_bill_1m"]) / 1e6)
            assert effective == pytest.approx(1.2 * published, abs=2e-5)
        elif row["level"] != "national":
            assert effective == pytest.approx(published)


def test_fitout_index_is_the_dod_construction_area_cost_factor() -> None:
    # DoD UFS 3-701-01 (6 June 2026) Table 4-1 CONUS MILCON ACF.
    expected = {
        "10001": ("county", "36061", 1.32),
        "94402": ("county", "06081", 1.23),
        "94103": ("county", "06075", 1.32),
        "78701": ("county", "48453", 0.82),
        "33139": ("county", "12086", 0.87),
        "82401": ("county", "56043", 1.05),
    }
    for zip_code, (tier, geography_id, factor) in expected.items():
        cost = resolve_construction_cost(resolve_zip(zip_code))
        assert cost.tier == tier, zip_code
        assert cost.geography_id == geography_id, zip_code
        assert cost.fitout_index == pytest.approx(factor), zip_code
        assert cost.source == "dod_ufs_3_701_01_2026"
        assert cost.fallback is False
    manhattan = resolve_construction_cost(resolve_zip("10001"))
    assert manhattan.fitout_index > 1.1 * manhattan.bea.fitout_index


def test_bea_goods_parity_is_only_the_fitout_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    import dce.data.construction_cost as construction
    from dce.model.types import GeoContext

    # Puerto Rico is in neither the DoD CONUS table nor the BEA seed.
    island = resolve_construction_cost(GeoContext("00601", "00601", "72001", "", "PR"))
    assert island.tier == "national"
    assert island.fitout_index == pytest.approx(1.0)

    # Take Wyoming out of the DoD table: the BEA state parity is the fallback.
    full = construction._load()
    trimmed = replace(
        full,
        county={k: v for k, v in full.county.items() if not k.startswith("56")},
        state={k: v for k, v in full.state.items() if k != "WY"},
    )
    monkeypatch.setattr(construction, "_load", lambda: trimmed)
    worland = resolve_construction_cost(resolve_zip("82401"))
    assert worland.tier == "bea_state"
    assert worland.source == "bea_rpp_goods_2024"
    assert worland.fallback is True
    assert worland.fitout_index == pytest.approx(worland.bea.fitout_index)
    assert worland.fitout_index == pytest.approx(
        resolve_price_index(resolve_zip("82401")).fitout_index
    )


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
