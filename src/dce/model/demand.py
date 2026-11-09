"""Annual delivery proxy.

Contract
--------
``estimate_annual_deliveries(demand, assumptions) -> float``

A constant-elasticity index around a reference ("median") site::

    ev_share = ev_stock / total_ldv
    score    = Π (x_i / reference_i) ** elasticity_i     for
               x = catchment_population, median_hh_income, ev_share, mean_commute
    score    = clamp(score, score_min, score_max)
    deliveries = base_annual_deliveries × score

A site that matches every reference value scores exactly 1 and gets
``base_annual_deliveries`` (plan assumption A9, an open product decision).
Elasticities and references are Jacob-tunable values in the assumptions
table, not Tesla data.

``DemandInputs.population`` (the center ZIP alone) is validated but does
not enter the score: the catchment total already includes it. It must not
exceed ``catchment_population``.

``apply_delivery_shock(deliveries, scenario) -> float``
    ``deliveries × (1 + scenario.delivery_shock)``. Kept separate so the
    contract signature above stays scenario-free; the M4 grid calls both.

Pure function. No I/O, no network, no LLM.
"""

from __future__ import annotations

from dce.model import _validate as v
from dce.model.assumptions import DemandFactor, ModelAssumptions, parse_assumptions
from dce.model.errors import InvalidInputError
from dce.model.types import Assumptions, DemandInputs, Scenario


def ev_share(demand: DemandInputs) -> float:
    """Return EVs as a fraction of light-duty vehicles in the catchment."""
    total = v.positive("demand.total_ldv", demand.total_ldv)
    evs = v.non_negative("demand.ev_stock", demand.ev_stock)
    if evs > total:
        raise InvalidInputError(
            f"demand.ev_stock ({evs}) must not exceed demand.total_ldv ({total})"
        )
    return evs / total


def demand_score(demand: DemandInputs, assumptions: Assumptions | ModelAssumptions) -> float:
    """Return the clamped demand index (1.0 at the reference site)."""
    params = parse_assumptions(assumptions).demand
    population = v.non_negative("demand.population", demand.population)
    catchment = v.positive("demand.catchment_population", demand.catchment_population)
    if population > catchment:
        raise InvalidInputError(
            f"demand.population ({population}) must not exceed "
            f"demand.catchment_population ({catchment})"
        )
    income = v.positive("demand.median_hh_income", demand.median_hh_income)
    commute = v.positive("demand.mean_commute", demand.mean_commute)
    share = ev_share(demand)

    score = (
        _term("catchment_population", catchment, params.catchment_population)
        * _term("median_hh_income", income, params.median_hh_income)
        * _term("ev_share", share, params.ev_share)
        * _term("mean_commute", commute, params.mean_commute)
    )
    return min(max(score, params.score_min), params.score_max)


def estimate_annual_deliveries(
    demand: DemandInputs, assumptions: Assumptions | ModelAssumptions
) -> float:
    """Return estimated annual deliveries for one catchment (before any scenario shock)."""
    parsed = parse_assumptions(assumptions)
    return parsed.demand.base_annual_deliveries * demand_score(demand, parsed)


def apply_delivery_shock(deliveries: float, scenario: Scenario) -> float:
    """Scale deliveries by ``1 + scenario.delivery_shock``."""
    base = v.non_negative("deliveries", deliveries)
    return base * (1.0 + v.shock("scenario.delivery_shock", scenario.delivery_shock))


def _term(name: str, value: float, factor: DemandFactor) -> float:
    if value == 0.0:
        if factor.elasticity < 0:
            raise InvalidInputError(
                f"demand {name} is 0 with a negative elasticity; the score is undefined"
            )
        return 0.0 if factor.elasticity > 0 else 1.0
    return float((value / factor.reference) ** factor.elasticity)
