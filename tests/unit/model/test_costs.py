"""Annualized cost components and cost per delivery."""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

import pytest

from dce.model.assumptions import ModelAssumptions
from dce.model.costs import (
    COMPONENT_KEYS,
    annualized_components,
    annualized_total,
    build_cost_inputs,
    cost_per_delivery,
    staffing_headcount,
    upfront_capex,
)
from dce.model.errors import InvalidInputError, ModelError, ZeroDeliveriesError
from dce.model.types import CostInputs, Scenario

# Round numbers so every component is easy to check by hand.
SIMPLE = CostInputs(
    sqft=10_000.0,
    rent_psf_month=2.0,
    opex_load=0.10,
    wage_annual=50_000.0,
    wage_load=1.20,
    headcount=10.0,
    kwh_per_year=100_000.0,
    energy_rate_kwh=0.20,
    demand_kw=50.0,
    demand_rate_kw=20.0,
    property_tax_annual=30_000.0,
    capex_total=1_000_000.0,
    capex_years=10.0,
    other_opex_annual=40_000.0,
)
BASE = Scenario(vehicle_mix={"model_y": 1.0}, wage_shock=0.0)


def test_components_by_hand() -> None:
    got = annualized_components(SIMPLE, BASE)
    assert tuple(got) == COMPONENT_KEYS
    assert got["lease"] == pytest.approx(2.0 * 12 * 10_000 * 1.10)  # 264,000
    assert got["labor"] == pytest.approx(10 * 50_000 * 1.20)  # 600,000
    assert got["utilities"] == pytest.approx(100_000 * 0.20 + 50 * 20 * 12)  # 32,000
    assert got["property_tax"] == 30_000.0
    assert got["capex"] == 100_000.0
    assert got["other_opex"] == 40_000.0


def test_cost_per_delivery_by_hand() -> None:
    components = annualized_components(SIMPLE, BASE)
    assert annualized_total(components) == pytest.approx(1_066_000.0)
    assert cost_per_delivery(components, 2_000.0) == pytest.approx(533.0)


def test_wage_shock_changes_labor_only() -> None:
    base = annualized_components(SIMPLE, BASE)
    up = annualized_components(SIMPLE, dataclasses.replace(BASE, wage_shock=0.2))
    down = annualized_components(SIMPLE, dataclasses.replace(BASE, wage_shock=-0.2))
    assert up["labor"] == pytest.approx(base["labor"] * 1.2)
    assert down["labor"] == pytest.approx(base["labor"] * 0.8)
    for key in COMPONENT_KEYS:
        if key != "labor":
            assert up[key] == base[key]
            assert down[key] == base[key]
    assert up["lease"] == base["lease"]


def test_rent_shock_changes_lease_only() -> None:
    base = annualized_components(SIMPLE, BASE)
    shocked = annualized_components(SIMPLE, dataclasses.replace(BASE, rent_shock=0.2))
    assert shocked["lease"] == pytest.approx(base["lease"] * 1.2)
    assert {k: v for k, v in shocked.items() if k != "lease"} == {
        k: v for k, v in base.items() if k != "lease"
    }


def test_vehicle_mix_and_delivery_shock_do_not_touch_m3_costs() -> None:
    base = annualized_components(SIMPLE, BASE)
    other = Scenario(vehicle_mix={"cybertruck": 1.0}, wage_shock=0.0, delivery_shock=0.5)
    assert annualized_components(SIMPLE, other) == base


@pytest.mark.parametrize("deliveries", [0.0, 0, -0.0, -5.0])
def test_zero_or_negative_deliveries_raise_typed_error(deliveries: float) -> None:
    components = annualized_components(SIMPLE, BASE)
    with pytest.raises(ZeroDeliveriesError) as info:
        cost_per_delivery(components, deliveries)
    assert info.value.deliveries == deliveries
    assert "deliveries > 0" in str(info.value)
    assert isinstance(info.value, ModelError)
    assert isinstance(info.value, ValueError)


@pytest.mark.parametrize("deliveries", [float("nan"), float("inf")])
def test_non_finite_deliveries_raise(deliveries: float) -> None:
    with pytest.raises(InvalidInputError, match="finite"):
        cost_per_delivery({"lease": 1.0}, deliveries)


def test_cost_per_delivery_rejects_bad_components() -> None:
    with pytest.raises(InvalidInputError, match="empty"):
        cost_per_delivery({}, 10.0)
    with pytest.raises(InvalidInputError, match="lease"):
        cost_per_delivery({"lease": -1.0}, 10.0)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"sqft": 0.0}, "sqft must be > 0"),
        ({"rent_psf_month": -1.0}, "rent_psf_month must be >= 0"),
        ({"wage_load": 0.3}, "multiplier"),
        ({"capex_years": 0.0}, "capex_years must be > 0"),
        ({"headcount": float("inf")}, "finite"),
        ({"other_opex_annual": -1.0}, "other_opex_annual"),
    ],
)
def test_bad_cost_inputs_raise(changes: dict[str, float], message: str) -> None:
    with pytest.raises(InvalidInputError, match=message):
        annualized_components(dataclasses.replace(SIMPLE, **changes), BASE)


def test_shock_of_minus_100_percent_is_rejected() -> None:
    with pytest.raises(InvalidInputError, match="wage_shock"):
        annualized_components(SIMPLE, dataclasses.replace(BASE, wage_shock=-1.0))


def test_staffing_floor_and_slope(assumptions: ModelAssumptions) -> None:
    assert staffing_headcount(0.0, assumptions) == 10.0
    assert staffing_headcount(3_000.0, assumptions) == 10.0
    assert staffing_headcount(6_000.0, assumptions) == pytest.approx(20.0)


def test_build_cost_inputs_from_assumptions(assumptions: ModelAssumptions) -> None:
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=1.5,
        wage_annual=60_000.0,
        energy_rate_kwh=0.25,
        demand_rate_kw=20.0,
        annual_deliveries=2_500.0,
    )
    assert costs.sqft == 25_000
    assert costs.rent_psf_month == 1.5
    assert costs.headcount == pytest.approx(10.0)
    assert costs.kwh_per_year == pytest.approx(375_000.0)
    assert costs.demand_kw == pytest.approx(150.0)
    # NNN rent already carries the landlord's property tax (included_in_nnn).
    assert costs.property_tax_annual == 0.0
    # 100 $/SF x 25,000 SF x 1.20 soft/contingency + $780k equipment.
    assert costs.capex_total == pytest.approx(3_780_000.0)
    assert costs.capex_years == 10
    lease = 1.5 * 12 * 25_000 * 1.15
    labor = 10 * 60_000 * 1.35
    assert costs.other_opex_annual == pytest.approx(0.08 * (lease + labor))


def test_other_opex_does_not_move_with_wage_shock(assumptions: ModelAssumptions) -> None:
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=1.5,
        wage_annual=60_000.0,
        energy_rate_kwh=0.25,
        demand_rate_kw=20.0,
        annual_deliveries=2_500.0,
    )
    base = annualized_components(costs, BASE)
    up = annualized_components(costs, dataclasses.replace(BASE, wage_shock=0.2))
    assert up["other_opex"] == base["other_opex"]


def test_build_cost_inputs_rejects_bad_resolved_values(assumptions: ModelAssumptions) -> None:
    with pytest.raises(InvalidInputError, match="rent_psf_month"):
        build_cost_inputs(
            assumptions,
            rent_psf_month=float("nan"),
            wage_annual=60_000.0,
            energy_rate_kwh=0.25,
            demand_rate_kw=20.0,
            annual_deliveries=2_500.0,
        )


def test_property_tax_is_charged_when_not_in_nnn(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    raw["property_tax"]["included_in_nnn"] = False
    costs = build_cost_inputs(
        raw,
        rent_psf_month=1.5,
        wage_annual=60_000.0,
        energy_rate_kwh=0.25,
        demand_rate_kw=20.0,
        annual_deliveries=2_500.0,
    )
    assert costs.property_tax_annual == pytest.approx(250 * 25_000 * 0.011)


def test_upfront_capex_splits_improvements_and_equipment(assumptions: ModelAssumptions) -> None:
    improvements, equipment = upfront_capex(assumptions)
    assert improvements == pytest.approx(3_000_000.0)
    assert equipment == pytest.approx(780_000.0)
    assert upfront_capex(assumptions, 10_000.0)[0] == pytest.approx(1_200_000.0)
