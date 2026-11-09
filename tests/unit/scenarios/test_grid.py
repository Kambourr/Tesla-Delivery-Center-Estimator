"""Scenario grid and low / base / high outcomes on the San Mateo fixtures."""

from __future__ import annotations

import dataclasses

import pytest
from scenario_data import GEO, STEADY, san_mateo_costs

from dce.model.assumptions import ModelAssumptions
from dce.model.dcf import build_dcf_inputs, run_dcf_views
from dce.model.errors import InvalidInputError
from dce.model.types import CostInputs, Scenario
from dce.scenarios import ranges as r
from dce.scenarios.grid import (
    WAGE_SHOCK,
    alternate_mix,
    apply_dcf_shocks,
    compose_shocks,
    costs_at,
    expand_default_scenarios,
    outcome_scenarios,
    run_scenario,
    run_scenario_grid,
)
from dce.scenarios.robustness import driver_rank_stability
from dce.scenarios.types import DcfShocks, NamedScenario, ScenarioResult

M4_IDS = [
    "baseline",
    "wage_minus_20",
    "wage_plus_20",
    "alt_mix",
    "wacc_low",
    "wacc_high",
    "growth_low",
    "growth_high",
]


def _grid(
    assumptions: ModelAssumptions, costs: CostInputs, named: list[NamedScenario]
) -> dict[str, ScenarioResult]:
    results = run_scenario_grid(GEO, STEADY, costs, named, assumptions)
    assert [res.scenario_id for res in results] == [n.scenario_id for n in named]
    return {res.scenario_id: res for res in results}


# -- expand_default_scenarios ----------------------------------------------------------


def test_default_grid_has_the_m4_cases(assumptions: ModelAssumptions) -> None:
    grid = expand_default_scenarios(assumptions.vehicle_mix, assumptions)
    by_id = {n.scenario_id: n for n in grid}
    assert [n.scenario_id for n in grid] == M4_IDS

    assert by_id["baseline"].scenario == Scenario(dict(assumptions.vehicle_mix), 0.0)
    assert by_id["baseline"].dcf == DcfShocks()
    assert by_id["wage_minus_20"].scenario.wage_shock == -WAGE_SHOCK == -0.20
    assert by_id["wage_plus_20"].scenario.wage_shock == 0.20
    assert by_id["wacc_low"].dcf == DcfShocks(discount_rate=0.097)
    assert by_id["wacc_high"].dcf == DcfShocks(discount_rate=0.163)
    assert by_id["growth_low"].dcf == DcfShocks(growth=0.0)
    assert by_id["growth_high"].dcf == DcfShocks(growth=0.10)
    assert by_id["wacc_low"].label == "WACC 9.7%"
    assert by_id["growth_low"].label == "Growth 0%"
    assert by_id["growth_high"].label == "Growth 10%"
    # Only the wage cases and the mix touch the operating Scenario.
    for sid in ("wacc_low", "wacc_high", "growth_low", "growth_high"):
        assert by_id[sid].scenario == by_id["baseline"].scenario


def test_alternate_mix_swaps_the_two_largest_shares(assumptions: ModelAssumptions) -> None:
    alt = alternate_mix(assumptions.vehicle_mix)
    assert alt["model_y"] == 0.27
    assert alt["model_3"] == 0.70
    assert alt["cybertruck"] == 0.03
    assert sum(alt.values()) == pytest.approx(1.0)
    assert assumptions.vehicle_mix["model_y"] == 0.70  # input not mutated


@pytest.mark.parametrize(
    "mix",
    [{}, {"model_y": 1.0}, {"model_y": 0.5, "model_3": 0.4}, {"model_y": 1.2, "model_3": -0.2}],
)
def test_bad_mix_raises(mix: dict[str, float], assumptions: ModelAssumptions) -> None:
    with pytest.raises(InvalidInputError):
        expand_default_scenarios(mix, assumptions)


# -- outcome_scenarios ------------------------------------------------------------------


def test_outcomes_low_is_bad_and_high_is_good(assumptions: ModelAssumptions) -> None:
    low, base, high = outcome_scenarios(assumptions)
    assert (low.scenario_id, base.scenario_id, high.scenario_id) == ("low", "base", "high")

    assert low.scenario.delivery_shock == pytest.approx(3_000 / 4_500 - 1)
    assert low.scenario.rent_shock == pytest.approx(2.95 / 2.14 - 1)
    assert low.scenario.wage_shock == pytest.approx(31.09 / 25.91 - 1)
    assert low.scenario.wage_shock == pytest.approx(0.20, abs=1e-3)
    assert low.dcf == DcfShocks(discount_rate=0.163, horizon_years=8, fee_per_delivery=1_250)

    assert base.scenario == Scenario(dict(assumptions.vehicle_mix), 0.0)
    assert base.dcf == DcfShocks(discount_rate=0.136, horizon_years=10, fee_per_delivery=1_390)

    assert high.scenario.delivery_shock == pytest.approx(6_500 / 4_500 - 1)
    assert high.scenario.rent_shock == pytest.approx(1.74 / 2.14 - 1)
    assert high.scenario.wage_shock == pytest.approx(20.73 / 25.91 - 1)
    assert high.dcf == DcfShocks(discount_rate=0.097, horizon_years=15, fee_per_delivery=1_640)


def test_outcome_volumes_hit_research_deliveries_at_the_range_base(
    assumptions: ModelAssumptions,
) -> None:
    """At the 4,500 range base the low / base / high volumes are 3,000 / 4,500 / 6,500."""
    costs = san_mateo_costs(assumptions, 4_500.0)
    results = run_scenario_grid(GEO, 4_500.0, costs, outcome_scenarios(assumptions), assumptions)
    volumes = [res.result.estimated_annual_deliveries for res in results]
    assert volumes == pytest.approx([3_000.0, 4_500.0, 6_500.0])


def test_rent_ratio_cites_kidder_mathews() -> None:
    assert r.RENT_RATIO.low == pytest.approx(1.74 / 2.14)
    assert r.RENT_RATIO.base == 1.0
    assert r.RENT_RATIO.high == pytest.approx(2.95 / 2.14)
    assert "Kidder Mathews" in r.RENT_CITATION


# -- run_scenario_grid: San Mateo goldens ---------------------------------------------


def test_baseline_matches_the_model_called_directly(
    assumptions: ModelAssumptions, costs: CostInputs, baseline: Scenario
) -> None:
    grid = _grid(assumptions, costs, expand_default_scenarios(assumptions.vehicle_mix, assumptions))
    result = grid["baseline"].result
    direct = run_dcf_views(costs, assumptions, steady_deliveries=STEADY, scenario=baseline)
    assert result.dcf == direct
    assert result.geo == GEO
    assert result.estimated_annual_deliveries == STEADY
    assert result.cost_per_delivery == pytest.approx(561.94, abs=0.01)
    assert result.dcf is not None
    assert result.dcf.standalone.npv == pytest.approx(9.7e6, abs=0.1e6)


def test_outcome_goldens_san_mateo(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    """Low / base / high at the 4,400 research volume. Base is the dcf §4 case."""
    grid = _grid(assumptions, costs, outcome_scenarios(assumptions))
    low, base, high = (grid[sid].result for sid in ("low", "base", "high"))
    assert low.dcf is not None and base.dcf is not None and high.dcf is not None

    assert low.cost_per_delivery == pytest.approx(862.75, abs=0.01)
    assert base.cost_per_delivery == pytest.approx(561.94, abs=0.01)
    assert high.cost_per_delivery == pytest.approx(399.43, abs=0.01)

    s_low, s_base, s_high = low.dcf.standalone, base.dcf.standalone, high.dcf.standalone
    assert s_low.npv == pytest.approx(-0.438e6, abs=0.005e6)
    assert s_base.npv == pytest.approx(9.678e6, abs=0.005e6)
    assert s_high.npv == pytest.approx(42.011e6, abs=0.005e6)
    assert s_low.irr == pytest.approx(0.1248, abs=1e-3)
    assert s_base.irr == pytest.approx(0.6633, abs=1e-3)
    assert s_high.irr == pytest.approx(1.3826, abs=1e-3)
    assert s_low.simple_payback_years == pytest.approx(5.21, abs=0.01)
    assert s_low.discounted_payback_years is None  # never pays back at 16.3% in 8 years
    assert s_high.discounted_payback_years == pytest.approx(0.91, abs=0.01)

    assert (s_low.discount_rate, s_base.discount_rate, s_high.discount_rate) == (
        0.163,
        0.136,
        0.097,
    )
    assert [len(s.years) for s in (s_low, s_base, s_high)] == [9, 11, 16]
    assert s_low.npv < s_base.npv < s_high.npv
    assert low.dcf.incremental.npv == pytest.approx(-2.972e6, abs=0.005e6)
    assert high.dcf.incremental.npv == pytest.approx(-2.525e6, abs=0.005e6)


def test_base_outcome_equals_baseline(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    named = outcome_scenarios(assumptions) + expand_default_scenarios(
        assumptions.vehicle_mix, assumptions
    )
    grid = _grid(assumptions, costs, named)
    assert grid["base"].result == grid["baseline"].result


def test_wage_plus_20_does_not_change_lease_dollars(
    assumptions: ModelAssumptions, costs: CostInputs
) -> None:
    grid = _grid(assumptions, costs, expand_default_scenarios(assumptions.vehicle_mix, assumptions))
    base, up = grid["baseline"].result, grid["wage_plus_20"].result
    assert up.components["lease"] == base.components["lease"]
    assert up.components["labor"] == pytest.approx(base.components["labor"] * 1.2)
    assert up.components["other_opex"] == base.components["other_opex"]
    assert base.dcf is not None and up.dcf is not None
    for y_base, y_up in zip(base.dcf.standalone.years, up.dcf.standalone.years, strict=True):
        assert y_up.lease == y_base.lease
    assert up.dcf.standalone.npv < base.dcf.standalone.npv


def test_dcf_shocks_move_only_the_dcf(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    grid = _grid(assumptions, costs, expand_default_scenarios(assumptions.vehicle_mix, assumptions))
    base = grid["baseline"].result
    assert base.dcf is not None
    for sid in ("wacc_low", "wacc_high", "growth_low", "growth_high"):
        shocked = grid[sid].result
        assert shocked.components == base.components
        assert shocked.cost_per_delivery == base.cost_per_delivery
        assert shocked.dcf is not None
        assert shocked.dcf.standalone.npv != base.dcf.standalone.npv
    npv = {sid: grid[sid].result.dcf.standalone.npv for sid in grid}  # type: ignore[union-attr]
    assert npv["wacc_high"] == pytest.approx(8.30e6, abs=0.01e6)
    assert npv["wacc_low"] == pytest.approx(12.16e6, abs=0.01e6)
    assert npv["growth_low"] == pytest.approx(8.03e6, abs=0.01e6)
    assert npv["growth_high"] == pytest.approx(10.93e6, abs=0.01e6)
    assert grid["alt_mix"].result == dataclasses.replace(
        base, scenario=grid["alt_mix"].named.scenario
    )


def test_driver_rank_spearman_is_bounded(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    named = expand_default_scenarios(assumptions.vehicle_mix, assumptions) + outcome_scenarios(
        assumptions
    )
    results = run_scenario_grid(GEO, STEADY, costs, named, assumptions)
    stability = driver_rank_stability(results, "baseline")
    assert set(stability) == {n.scenario_id for n in named} - {"baseline"}
    assert all(-1.0 <= rho <= 1.0 for rho in stability.values())
    assert stability["wacc_high"] == 1.0  # a DCF shock cannot reorder cost components


def test_catchment_is_passed_through(
    assumptions: ModelAssumptions, costs: CostInputs, baseline: Scenario
) -> None:
    named = NamedScenario("baseline", "Baseline", baseline)
    assert run_scenario(GEO, STEADY, costs, named, assumptions).result.catchment is None


def test_duplicate_ids_raise(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    named = outcome_scenarios(assumptions)
    with pytest.raises(InvalidInputError, match="unique"):
        run_scenario_grid(GEO, STEADY, costs, [named[0], named[0]], assumptions)


def test_zero_volume_raises_cleanly(
    assumptions: ModelAssumptions, costs: CostInputs, baseline: Scenario
) -> None:
    from dce.model.errors import ZeroDeliveriesError

    with pytest.raises(ZeroDeliveriesError):
        run_scenario(GEO, 0.0, costs, NamedScenario("z", "Zero", baseline), assumptions)


# -- helpers ----------------------------------------------------------------------------


def test_apply_dcf_shocks(assumptions: ModelAssumptions) -> None:
    base = build_dcf_inputs(assumptions)
    assert apply_dcf_shocks(base, DcfShocks()) == base
    shocked = apply_dcf_shocks(
        base, DcfShocks(discount_rate=0.2, horizon_years=8, growth=0.0, fee_per_delivery=1_000)
    )
    assert (shocked.wacc, shocked.horizon_years, shocked.growth, shocked.fee_per_delivery) == (
        0.2,
        8,
        0.0,
        1_000,
    )
    assert (
        dataclasses.replace(
            shocked,
            wacc=base.wacc,
            horizon_years=base.horizon_years,
            growth=base.growth,
            fee_per_delivery=base.fee_per_delivery,
        )
        == base
    )


@pytest.mark.parametrize(
    "shocks",
    [
        DcfShocks(horizon_years=0),
        DcfShocks(horizon_years=True),
        DcfShocks(discount_rate=0.0),
        DcfShocks(growth=-1.0),
        DcfShocks(fee_per_delivery=-1.0),
    ],
)
def test_apply_dcf_shocks_rejects_bad_values(
    shocks: DcfShocks, assumptions: ModelAssumptions
) -> None:
    with pytest.raises(InvalidInputError):
        apply_dcf_shocks(build_dcf_inputs(assumptions), shocks)


def test_compose_shocks() -> None:
    assert compose_shocks() == 0.0
    assert compose_shocks(0.1, 0.2) == pytest.approx(0.32)
    with pytest.raises(InvalidInputError):
        compose_shocks(-1.0)


def test_costs_at_recomputes_headcount_and_other_opex(
    assumptions: ModelAssumptions, costs: CostInputs
) -> None:
    rebuilt = costs_at(costs, assumptions, 6_000.0)
    assert rebuilt == san_mateo_costs(assumptions, 6_000.0)
    assert costs_at(costs, assumptions, STEADY) == costs


def test_missing_range_raises(assumptions: ModelAssumptions) -> None:
    trimmed = {k: v for k, v in assumptions.ranges.items() if k != r.DISCOUNT_RATE}
    with pytest.raises(InvalidInputError, match="dcf.discount_rate"):
        expand_default_scenarios(
            assumptions.vehicle_mix, dataclasses.replace(assumptions, ranges=trimmed)
        )
