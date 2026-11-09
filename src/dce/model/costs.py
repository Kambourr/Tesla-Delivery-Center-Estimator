"""Annualized cost components and cost per delivery.

Contract
--------
``annualized_components(costs, scenario) -> dict[str, float]``
    Keys: ``lease``, ``labor``, ``utilities``, ``property_tax``, ``capex``,
    ``other_opex``. Lease is ``rent_psf_year × sqft × (1 + opex_load)``
    after converting monthly rent and applying ``scenario.rent_shock``.
    ``scenario.wage_shock`` scales labor unit cost only. A wage shock must
    not change lease dollars.

``cost_per_delivery(components, deliveries) -> float``
    ``sum(components) / deliveries``. Zero deliveries raises a clean error
    (defined in M3, not here).

Pure. No I/O, no network, no LLM.

Milestone M0: both functions raise ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import CostInputs, Scenario


def annualized_components(costs: CostInputs, scenario: Scenario) -> dict[str, float]:
    """Return annualized dollars by component. Not implemented in M0."""
    raise NotImplementedError("dce.model.costs.annualized_components is a stub (M0)")


def cost_per_delivery(components: dict[str, float], deliveries: float) -> float:
    """Return annualized total divided by deliveries. Not implemented in M0."""
    raise NotImplementedError("dce.model.costs.cost_per_delivery is a stub (M0)")
