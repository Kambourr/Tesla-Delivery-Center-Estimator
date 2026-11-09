"""Shared fixtures for the scenario tests."""

from __future__ import annotations

import pytest
from scenario_data import STEADY, load_assumptions, san_mateo_costs

from dce.model.assumptions import ModelAssumptions
from dce.model.types import CostInputs, Scenario
from dce.scenarios.tornado import TornadoInputs


@pytest.fixture
def assumptions() -> ModelAssumptions:
    return load_assumptions()


@pytest.fixture
def baseline(assumptions: ModelAssumptions) -> Scenario:
    return Scenario(vehicle_mix=dict(assumptions.vehicle_mix), wage_shock=0.0)


@pytest.fixture
def costs(assumptions: ModelAssumptions) -> CostInputs:
    return san_mateo_costs(assumptions)


@pytest.fixture
def tornado_inputs(
    costs: CostInputs, assumptions: ModelAssumptions, baseline: Scenario
) -> TornadoInputs:
    return TornadoInputs(
        costs=costs, assumptions=assumptions, steady_deliveries=STEADY, scenario=baseline
    )
