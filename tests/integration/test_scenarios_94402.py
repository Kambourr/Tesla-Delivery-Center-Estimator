"""Scenario grid and tornado on the full San Mateo 94402 pipeline. Fixtures only.

The test rebuilds the inputs ``estimate("94402")`` loads (gravity volume,
demo rent and PG&E rates, fallback wage) and checks that the scenario layer's
baseline reproduces ``estimate`` exactly. That is the contract an
orchestrator ``estimate_grid`` would rely on.
"""

from __future__ import annotations

import pytest
import yaml

from dce.config import assumptions_path
from dce.data.operating_inputs import load_san_mateo_operating_inputs
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.types import CostInputs
from dce.orchestrator import estimate
from dce.scenarios.grid import expand_default_scenarios, outcome_scenarios, run_scenario_grid
from dce.scenarios.robustness import driver_rank_stability
from dce.scenarios.tornado import TornadoInputs, dcf_tornado


def _inputs(steady: float) -> tuple[ModelAssumptions, CostInputs]:
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assumptions = parse_assumptions(raw)
    rates = load_san_mateo_operating_inputs()
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=rates.rent_psf_month,
        wage_annual=assumptions.labor.fallback_wage_hourly * assumptions.labor.paid_hours_per_fte,
        energy_rate_kwh=rates.energy_rate_kwh,
        demand_rate_kw=rates.demand_rate_kw,
        annual_deliveries=steady,
    )
    return assumptions, costs


def test_grid_baseline_reproduces_estimate_94402() -> None:
    base = estimate("94402")
    assert base.catchment is not None and base.dcf is not None
    steady = base.catchment.gravity.deliveries_per_year
    assumptions, costs = _inputs(steady)

    named = expand_default_scenarios(assumptions.vehicle_mix, assumptions) + outcome_scenarios(
        assumptions
    )
    results = {
        res.scenario_id: res
        for res in run_scenario_grid(
            base.geo, steady, costs, named, assumptions, catchment=base.catchment
        )
    }
    assert results["baseline"].result == base
    assert results["base"].result == base

    low = results["low"].result.dcf
    high = results["high"].result.dcf
    assert low is not None and high is not None
    assert low.standalone.npv < base.dcf.standalone.npv < high.standalone.npv
    assert results["low"].result.estimated_annual_deliveries == pytest.approx(steady * 2 / 3)

    stability = driver_rank_stability(list(results.values()), "baseline")
    assert all(-1.0 <= rho <= 1.0 for rho in stability.values())


def test_tornado_94402_ranks_deliveries_first_and_brackets_base() -> None:
    base = estimate("94402")
    assert base.catchment is not None and base.dcf is not None
    steady = base.catchment.gravity.deliveries_per_year
    assumptions, costs = _inputs(steady)

    bars = dcf_tornado(
        TornadoInputs(
            costs=costs,
            assumptions=assumptions,
            steady_deliveries=steady,
            scenario=base.scenario,
        )
    )
    assert bars[0].driver == "deliveries"
    for bar in bars:
        assert bar.npv_base == base.dcf.standalone.npv
        assert bar.npv_low <= bar.npv_base <= bar.npv_high, bar.driver
