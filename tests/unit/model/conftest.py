"""Shared fixtures for the pure-model tests."""

from __future__ import annotations

from typing import Any

import pytest
from m3_data import demand_from, load_frozen_inputs, load_raw_assumptions

from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.types import DemandInputs, Scenario


@pytest.fixture
def raw_assumptions() -> dict[str, Any]:
    return load_raw_assumptions()


@pytest.fixture
def assumptions() -> ModelAssumptions:
    return parse_assumptions(load_raw_assumptions())


@pytest.fixture
def frozen_inputs() -> dict[str, Any]:
    return load_frozen_inputs()


@pytest.fixture
def demand_inputs(frozen_inputs: dict[str, Any]) -> DemandInputs:
    return demand_from(frozen_inputs["demand"])


@pytest.fixture
def base_scenario() -> Scenario:
    return Scenario(vehicle_mix={"model_y": 1.0}, wage_shock=0.0)
