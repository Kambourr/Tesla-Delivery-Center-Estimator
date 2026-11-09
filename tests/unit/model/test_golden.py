"""M3 acceptance: frozen inputs + shipped assumptions reproduce the golden JSON.

Regenerate the golden only on purpose (after bumping ``assumptions_version``
or changing the formulas), then review the diff::

    DCE_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/unit/model/test_golden.py
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

import pytest
from m3_data import (
    GOLDEN,
    demand_from,
    load_frozen_inputs,
    load_raw_assumptions,
    scenario_from,
)

from dce.model.assumptions import parse_assumptions
from dce.model.costs import annualized_components, build_cost_inputs, cost_per_delivery
from dce.model.demand import apply_delivery_shock, estimate_annual_deliveries
from dce.model.drivers import top_drivers


def _compute() -> dict[str, Any]:
    assumptions = parse_assumptions(load_raw_assumptions())
    inputs = load_frozen_inputs()
    demand = demand_from(inputs["demand"])
    resolved = {k: float(v) for k, v in inputs["resolved"].items()}

    deliveries = estimate_annual_deliveries(demand, assumptions)
    costs = build_cost_inputs(assumptions, annual_deliveries=deliveries, **resolved)

    cases: dict[str, Any] = {}
    for scenario_id, spec in inputs["scenarios"].items():
        scenario = scenario_from(spec)
        shocked_deliveries = apply_delivery_shock(deliveries, scenario)
        components = annualized_components(costs, scenario)
        cases[scenario_id] = {
            "estimated_annual_deliveries": shocked_deliveries,
            "annualized_total_cost": math.fsum(components.values()),
            "cost_per_delivery": round(cost_per_delivery(components, shocked_deliveries), 2),
            "components": components,
            "drivers": [
                {"name": d.name, "usd": d.usd, "share": d.share} for d in top_drivers(components)
            ],
        }
    return {
        "assumptions_version": assumptions.assumptions_version,
        "headcount": costs.headcount,
        "cases": cases,
    }


def test_update_golden_when_asked() -> None:
    if os.environ.get("DCE_UPDATE_GOLDEN") != "1":
        pytest.skip("set DCE_UPDATE_GOLDEN=1 to rewrite golden_m3.json")
    GOLDEN.write_text(json.dumps(_compute(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


@pytest.fixture(scope="module")
def computed() -> dict[str, Any]:
    return _compute()


def test_golden_is_for_the_shipped_assumptions(
    golden: dict[str, Any], computed: dict[str, Any]
) -> None:
    assert computed["assumptions_version"] == golden["assumptions_version"], (
        "data/defaults/assumptions.yaml changed version; regenerate golden_m3.json on purpose"
    )


@pytest.mark.parametrize("scenario_id", ["base", "wage_p20", "rent_m20"])
def test_cost_per_delivery_matches_golden_to_two_decimals(
    golden: dict[str, Any], computed: dict[str, Any], scenario_id: str
) -> None:
    want = golden["cases"][scenario_id]["cost_per_delivery"]
    got = computed["cases"][scenario_id]["cost_per_delivery"]
    assert round(got, 2) == round(want, 2)


@pytest.mark.parametrize("scenario_id", ["base", "wage_p20", "rent_m20"])
def test_components_and_drivers_match_golden(
    golden: dict[str, Any], computed: dict[str, Any], scenario_id: str
) -> None:
    want = golden["cases"][scenario_id]
    got = computed["cases"][scenario_id]
    assert got["components"].keys() == want["components"].keys()
    for name, usd in want["components"].items():
        assert got["components"][name] == pytest.approx(usd, abs=0.005)
    assert got["annualized_total_cost"] == pytest.approx(want["annualized_total_cost"], abs=0.005)
    assert got["estimated_annual_deliveries"] == pytest.approx(
        want["estimated_annual_deliveries"], abs=1e-6
    )
    assert [d["name"] for d in got["drivers"]] == [d["name"] for d in want["drivers"]]
    for g, w in zip(got["drivers"], want["drivers"], strict=True):
        assert g["usd"] == pytest.approx(w["usd"], abs=0.005)
        assert g["share"] == pytest.approx(w["share"], abs=1e-9)


@pytest.mark.parametrize("scenario_id", ["base", "wage_p20", "rent_m20"])
def test_top3_shares_sum_to_at_most_one(golden: dict[str, Any], scenario_id: str) -> None:
    drivers = golden["cases"][scenario_id]["drivers"]
    assert len(drivers) == 3
    assert all(0.0 <= d["share"] <= 1.0 for d in drivers)
    assert sum(d["share"] for d in drivers) <= 1.0


def test_golden_matches_independent_hand_arithmetic(golden: dict[str, Any]) -> None:
    """Re-derive the base case with plain arithmetic, no dce imports, so the golden is not
    only the model checking itself. Numbers mirror assumptions.yaml 2026.11.0 and the
    frozen inputs."""
    score = (
        (750_000 / 500_000) ** 0.5
        * (140_000 / 80_000) ** 0.3
        * ((45_000 / 600_000) / 0.03) ** 0.5
        * (28 / 27) ** -0.25
    )
    deliveries = 2_500 * score
    headcount = max(8.0, deliveries / 250)
    lease = 1.58 * 12 * 25_000 * 1.15
    labor = headcount * 72_000 * 1.30
    utilities = 15 * 25_000 * 0.28 + 0.006 * 25_000 * 28 * 12
    property_tax = 250 * 25_000 * 0.011
    capex = 115 * 25_000 / 10
    other_opex = 0.08 * (lease + labor)
    total = lease + labor + utilities + property_tax + capex + other_opex

    base = golden["cases"]["base"]
    assert golden["assumptions_version"] == "2026.11.0"
    assert base["estimated_annual_deliveries"] == pytest.approx(deliveries, rel=1e-12)
    assert base["annualized_total_cost"] == pytest.approx(total, abs=0.005)
    assert base["cost_per_delivery"] == round(total / deliveries, 2)
