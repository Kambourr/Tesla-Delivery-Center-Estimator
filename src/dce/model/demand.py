"""Annual delivery proxy.

Contract
--------
``estimate_annual_deliveries(demand, assumptions) -> float``

Pure function. ``deliveries ≈ base_throughput × f(income, ev_stock,
population, commute)`` using :class:`~dce.model.types.DemandInputs` and the
Jacob-tunable assumption table (base throughput is an open product
decision; the placeholder in the plan is 2,500 at a median score).

No I/O, no network, no LLM.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import DemandInputs


def estimate_annual_deliveries(demand: DemandInputs, assumptions: dict) -> float:
    """Return estimated annual deliveries. Not implemented in M0."""
    raise NotImplementedError("dce.model.demand.estimate_annual_deliveries is a stub (M0)")
