"""Scenario grid, low / base / high outcomes, NPV tornado, and rank-stability checks.

Contract: call ``dce.model`` on inputs the orchestrator already loaded.
No file I/O, no SQLite, no network, no GUI, and no LLM. Wage shocks must
not be implemented here by re-reading rent from disk; the model applies
``Scenario.wage_shock`` to labor only.
"""

from dce.scenarios.grid import (
    apply_dcf_shocks,
    expand_default_scenarios,
    outcome_scenarios,
    run_scenario,
    run_scenario_grid,
)
from dce.scenarios.robustness import (
    driver_rank_stability,
    npv_driver_rank_stability,
    spearman_rank_corr,
)
from dce.scenarios.tornado import TornadoInputs, dcf_tornado, tornado_rows
from dce.scenarios.types import DcfShocks, NamedScenario, ScenarioResult, TornadoBar

__all__ = [
    "DcfShocks",
    "NamedScenario",
    "ScenarioResult",
    "TornadoBar",
    "TornadoInputs",
    "apply_dcf_shocks",
    "dcf_tornado",
    "driver_rank_stability",
    "expand_default_scenarios",
    "npv_driver_rank_stability",
    "outcome_scenarios",
    "run_scenario",
    "run_scenario_grid",
    "spearman_rank_corr",
    "tornado_rows",
]
