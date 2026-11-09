"""File loaders for the pure-model tests. File reads happen here, never in ``dce.model``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from dce.model.types import DemandInputs, Scenario

REPO = Path(__file__).resolve().parents[3]
ASSUMPTIONS_YAML = REPO / "data" / "defaults" / "assumptions.yaml"
FIXTURES = REPO / "tests" / "fixtures" / "model"
FROZEN_INPUTS = FIXTURES / "m3_frozen_inputs.json"
GOLDEN = FIXTURES / "golden_m3.json"


def load_raw_assumptions() -> dict[str, Any]:
    raw = yaml.safe_load(ASSUMPTIONS_YAML.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def load_frozen_inputs() -> dict[str, Any]:
    payload = json.loads(FROZEN_INPUTS.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def demand_from(spec: dict[str, Any]) -> DemandInputs:
    return DemandInputs(**{k: float(v) for k, v in spec.items()})


def scenario_from(spec: dict[str, Any]) -> Scenario:
    return Scenario(
        vehicle_mix=dict(spec["vehicle_mix"]),
        wage_shock=float(spec["wage_shock"]),
        rent_shock=float(spec.get("rent_shock", 0.0)),
        delivery_shock=float(spec.get("delivery_shock", 0.0)),
    )
