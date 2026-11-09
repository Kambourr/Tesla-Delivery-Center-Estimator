"""Demand proxy: constant-elasticity score around a reference site."""

from __future__ import annotations

import dataclasses

import pytest

from dce.model.assumptions import ModelAssumptions
from dce.model.demand import (
    apply_delivery_shock,
    demand_score,
    estimate_annual_deliveries,
    ev_share,
)
from dce.model.errors import InvalidInputError
from dce.model.types import DemandInputs, Scenario


def _reference_site(a: ModelAssumptions) -> DemandInputs:
    f = a.demand
    total_ldv = 100_000.0
    return DemandInputs(
        population=10_000.0,
        median_hh_income=f.median_hh_income.reference,
        ev_stock=f.ev_share.reference * total_ldv,
        total_ldv=total_ldv,
        mean_commute=f.mean_commute.reference,
        catchment_population=f.catchment_population.reference,
    )


def test_reference_site_gets_base_deliveries(assumptions: ModelAssumptions) -> None:
    site = _reference_site(assumptions)
    assert demand_score(site, assumptions) == pytest.approx(1.0)
    assert estimate_annual_deliveries(site, assumptions) == pytest.approx(4_500.0)


def test_accepts_raw_mapping(
    raw_assumptions: dict[str, object], demand_inputs: DemandInputs
) -> None:
    from dce.model.assumptions import parse_assumptions

    parsed = parse_assumptions(raw_assumptions)
    assert estimate_annual_deliveries(demand_inputs, raw_assumptions) == estimate_annual_deliveries(
        demand_inputs, parsed
    )


def test_is_deterministic(assumptions: ModelAssumptions, demand_inputs: DemandInputs) -> None:
    runs = {estimate_annual_deliveries(demand_inputs, assumptions) for _ in range(5)}
    assert len(runs) == 1


@pytest.mark.parametrize(
    ("field", "factor", "direction"),
    [
        ("catchment_population", 2.0, 1),
        ("median_hh_income", 2.0, 1),
        ("ev_stock", 2.0, 1),
        ("mean_commute", 2.0, -1),
    ],
)
def test_each_factor_moves_demand_the_documented_way(
    assumptions: ModelAssumptions,
    demand_inputs: DemandInputs,
    field: str,
    factor: float,
    direction: int,
) -> None:
    base = estimate_annual_deliveries(demand_inputs, assumptions)
    bumped = dataclasses.replace(demand_inputs, **{field: getattr(demand_inputs, field) * factor})
    moved = estimate_annual_deliveries(bumped, assumptions)
    assert (moved - base) * direction > 0


def test_center_zip_population_does_not_change_score(
    assumptions: ModelAssumptions, demand_inputs: DemandInputs
) -> None:
    other = dataclasses.replace(demand_inputs, population=demand_inputs.population / 2)
    assert estimate_annual_deliveries(other, assumptions) == estimate_annual_deliveries(
        demand_inputs, assumptions
    )


def test_score_is_clamped(assumptions: ModelAssumptions, demand_inputs: DemandInputs) -> None:
    huge = dataclasses.replace(demand_inputs, catchment_population=1e12, population=0.0)
    assert demand_score(huge, assumptions) == assumptions.demand.score_max


def test_zero_evs_gives_zero_deliveries(
    assumptions: ModelAssumptions, demand_inputs: DemandInputs
) -> None:
    none = dataclasses.replace(demand_inputs, ev_stock=0.0)
    assert ev_share(none) == 0.0
    assert estimate_annual_deliveries(none, assumptions) == 0.0


def test_zero_with_negative_elasticity_is_rejected(
    assumptions: ModelAssumptions, demand_inputs: DemandInputs
) -> None:
    flipped = dataclasses.replace(
        assumptions,
        demand=dataclasses.replace(
            assumptions.demand,
            ev_share=dataclasses.replace(assumptions.demand.ev_share, elasticity=-0.5),
        ),
    )
    with pytest.raises(InvalidInputError, match="negative elasticity"):
        demand_score(dataclasses.replace(demand_inputs, ev_stock=0.0), flipped)


def test_zero_elasticity_ignores_a_zero_value(
    assumptions: ModelAssumptions, demand_inputs: DemandInputs
) -> None:
    flat = dataclasses.replace(
        assumptions,
        demand=dataclasses.replace(
            assumptions.demand,
            ev_share=dataclasses.replace(assumptions.demand.ev_share, elasticity=0.0),
        ),
    )
    assert demand_score(dataclasses.replace(demand_inputs, ev_stock=0.0), flat) > 0


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"total_ldv": 0.0}, "total_ldv must be > 0"),
        ({"ev_stock": -1.0}, "ev_stock must be >= 0"),
        ({"ev_stock": 700_000.0}, "must not exceed demand.total_ldv"),
        ({"catchment_population": 0.0}, "catchment_population must be > 0"),
        ({"population": 1e9}, "must not exceed demand.catchment_population"),
        ({"median_hh_income": float("nan")}, "finite"),
        ({"mean_commute": 0.0}, "mean_commute must be > 0"),
    ],
)
def test_bad_inputs_raise(
    assumptions: ModelAssumptions,
    demand_inputs: DemandInputs,
    changes: dict[str, float],
    message: str,
) -> None:
    with pytest.raises(InvalidInputError, match=message):
        estimate_annual_deliveries(dataclasses.replace(demand_inputs, **changes), assumptions)


def test_delivery_shock_scales_deliveries() -> None:
    up = Scenario(vehicle_mix={}, wage_shock=0.0, delivery_shock=0.2)
    assert apply_delivery_shock(1_000.0, up) == pytest.approx(1_200.0)
    flat = Scenario(vehicle_mix={}, wage_shock=0.0)
    assert apply_delivery_shock(1_000.0, flat) == 1_000.0


def test_delivery_shock_of_minus_100_percent_is_rejected() -> None:
    gone = Scenario(vehicle_mix={}, wage_shock=0.0, delivery_shock=-1.0)
    with pytest.raises(InvalidInputError, match="delivery_shock"):
        apply_delivery_shock(1_000.0, gone)
