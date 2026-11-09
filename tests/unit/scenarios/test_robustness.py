"""Spearman rank checks for cost components and NPV drivers."""

from __future__ import annotations

import dataclasses

import pytest
from scenario_data import GEO, STEADY

from dce.model.assumptions import ModelAssumptions
from dce.model.dcf import build_dcf_inputs
from dce.model.errors import InvalidInputError
from dce.model.types import CostInputs
from dce.scenarios.grid import expand_default_scenarios, run_scenario_grid
from dce.scenarios.robustness import (
    component_ranking,
    driver_rank_stability,
    npv_driver_rank_stability,
    spearman_rank_corr,
    tornado_ranking,
)
from dce.scenarios.tornado import TornadoInputs, dcf_tornado


def test_spearman_identity_reverse_and_known_value() -> None:
    labels = ["a", "b", "c", "d"]
    assert spearman_rank_corr(labels, labels) == 1.0
    assert spearman_rank_corr(labels, labels[::-1]) == -1.0
    # One adjacent swap: Σd² = 2, n = 4 → 1 − 12 / 60 = 0.8.
    assert spearman_rank_corr(labels, ["b", "a", "c", "d"]) == pytest.approx(0.8)
    assert spearman_rank_corr(["a"], ["a"]) == 1.0
    assert spearman_rank_corr([], []) == 1.0


@pytest.mark.parametrize(
    ("a", "b", "match"),
    [
        (["a", "b"], ["a", "c"], "same labels"),
        (["a", "a"], ["a", "b"], "repeats"),
    ],
)
def test_spearman_rejects_mismatched_rankings(a: list[str], b: list[str], match: str) -> None:
    with pytest.raises(InvalidInputError, match=match):
        spearman_rank_corr(a, b)


def test_component_ranking_and_stability(assumptions: ModelAssumptions, costs: CostInputs) -> None:
    results = run_scenario_grid(
        GEO,
        STEADY,
        costs,
        expand_default_scenarios(assumptions.vehicle_mix, assumptions),
        assumptions,
    )
    ranking = component_ranking(results[0].result)
    assert ranking[:3] == ["labor", "lease", "capex"]
    assert sorted(ranking) == sorted(results[0].result.components)
    stability = driver_rank_stability(results, "baseline")
    assert "baseline" not in stability
    assert all(-1.0 <= rho <= 1.0 for rho in stability.values())
    with pytest.raises(InvalidInputError, match="baseline"):
        driver_rank_stability(results, "nope")
    with pytest.raises(InvalidInputError, match="unique"):
        driver_rank_stability([results[0], results[0]], "baseline")


def test_npv_driver_rank_stability(
    tornado_inputs: TornadoInputs, assumptions: ModelAssumptions
) -> None:
    base = dcf_tornado(tornado_inputs)
    high_wacc_dcf = dataclasses.replace(build_dcf_inputs(assumptions), wacc=0.163)
    high_wacc = dcf_tornado(dataclasses.replace(tornado_inputs, dcf=high_wacc_dcf))
    assert tornado_ranking(base)[0] == "deliveries"
    stability = npv_driver_rank_stability({"baseline": base, "wacc_high": high_wacc}, "baseline")
    assert list(stability) == ["wacc_high"]
    assert -1.0 <= stability["wacc_high"] <= 1.0
    assert stability["wacc_high"] > 0.8  # same story at a higher discount rate
