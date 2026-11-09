"""Scenario grid: vehicle mix and wage shocks.

Contract
--------
``expand_default_scenarios(base_mix) -> list[Scenario]``
    Baseline, wage −20%, wage +20%, and one alternate mix. Optional rent
    and delivery shocks use the same framework later; they are not required
    inputs.

``run_scenario_grid(geo, demand, costs, scenarios, assumptions) -> list[EstimateResult]``
    Recompute demand and cost for each scenario by calling the pure model
    functions. No I/O of its own: the orchestrator has already loaded inputs.
    No LLM.

Milestone M0: both functions raise ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import (
    CostInputs,
    DemandInputs,
    EstimateResult,
    GeoContext,
    Scenario,
)


def expand_default_scenarios(base_mix: dict[str, float]) -> list[Scenario]:
    """Build the default scenario list from a base vehicle mix. Not implemented in M0."""
    raise NotImplementedError("dce.model.scenarios.expand_default_scenarios is a stub (M0)")


def run_scenario_grid(
    geo: GeoContext,
    demand: DemandInputs,
    costs: CostInputs,
    scenarios: list[Scenario],
    assumptions: dict,
) -> list[EstimateResult]:
    """Evaluate every scenario. Not implemented in M0."""
    raise NotImplementedError("dce.model.scenarios.run_scenario_grid is a stub (M0)")
