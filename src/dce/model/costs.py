"""Annualized cost components and cost per delivery.

Contract
--------
``annualized_components(costs, scenario) -> dict[str, float]``
    Keys, in this order: ``lease``, ``labor``, ``utilities``,
    ``property_tax``, ``capex``, ``other_opex``. USD per year.

    ============  ==========================================================
    lease         rent_psf_month × 12 × (1 + rent_shock) × sqft × (1 + opex_load)
    labor         headcount × wage_annual × (1 + wage_shock) × wage_load
    utilities     kwh_per_year × energy_rate_kwh
                  + demand_kw × demand_rate_kw × 12   (monthly demand charge)
    property_tax  property_tax_annual
    capex         capex_total / capex_years            (straight line; the DCF
                  instead spends capex_total as year-0 cash, see dce.model.dcf)
    other_opex    other_opex_annual
    ============  ==========================================================

    ``opex_load`` is a fraction (0.15 means +15%). ``wage_load`` is a
    multiplier (1.30 means +30%) and must be at least 1. ``wage_shock``
    scales labor only and never changes lease dollars; ``rent_shock``
    scales lease only. ``Scenario.vehicle_mix`` does not enter M3 math (M4
    maps it to labor minutes and energy). ``delivery_shock`` is applied to
    deliveries by :func:`dce.model.demand.apply_delivery_shock`.

``cost_per_delivery(components, deliveries) -> float``
    ``sum(components) / deliveries``. ``deliveries <= 0`` raises
    :class:`~dce.model.errors.ZeroDeliveriesError`.

``build_cost_inputs(assumptions, *, rent_psf_month, wage_annual, energy_rate_kwh,
demand_rate_kw, annual_deliveries, opex_load=None, fitout_index=1, property_tax_rate=None)
-> CostInputs``
    Turns the assumptions table plus resolved public inputs into
    :class:`CostInputs`. Rent arrives as a number; this module never looks
    rent up. ``other_opex_annual`` is a percentage of baseline (unshocked)
    lease + labor, so a scenario shock does not move it. ``capex_total`` is
    :func:`upfront_capex` (improvements + equipment). ``property_tax_annual``
    is 0 when ``property_tax.included_in_nnn`` is true, because NNN rent's
    ``opex_load`` already carries the landlord's tax. ``opex_load`` replaces
    that fraction when a local tax rate has shifted it.
    ``fitout_index`` scales fit-out only (1 is the national assumption).
    ``property_tax_rate`` replaces the assumptions rate when tax is not
    inside NNN.

``upfront_capex(assumptions, sqft=None, *, fitout_index=1) -> tuple[float, float]``
    ``(improvements, equipment)`` in USD: ``fitout_psf × fitout_index × sqft ×
    (1 + soft_contingency)`` and ``equipment_usd``. Equipment is not indexed.

``nnn_opex_load(...) -> float``
    The NNN load after swapping the reference tax rate for a local one.
    At the reference rate the load is unchanged. A zero rent is not shifted.

Pure. No I/O, no network, no LLM.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from dce.model import _validate as v
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.errors import InvalidInputError, ZeroDeliveriesError
from dce.model.types import Assumptions, CostInputs, Scenario

MONTHS_PER_YEAR = 12.0

COMPONENT_KEYS: tuple[str, ...] = (
    "lease",
    "labor",
    "utilities",
    "property_tax",
    "capex",
    "other_opex",
)


def annual_lease(costs: CostInputs, rent_shock: float = 0.0) -> float:
    """Return annual occupancy cost: rent × sqft × (1 + opex_load), after a rent shock."""
    rent = v.non_negative("costs.rent_psf_month", costs.rent_psf_month)
    sqft = v.positive("costs.sqft", costs.sqft)
    load = v.non_negative("costs.opex_load", costs.opex_load)
    shocked = rent * MONTHS_PER_YEAR * (1.0 + v.shock("scenario.rent_shock", rent_shock))
    return shocked * sqft * (1.0 + load)


def annual_labor(costs: CostInputs, wage_shock: float = 0.0) -> float:
    """Return annual loaded labor cost after a wage shock."""
    headcount = v.non_negative("costs.headcount", costs.headcount)
    wage = v.non_negative("costs.wage_annual", costs.wage_annual)
    load = v.positive("costs.wage_load", costs.wage_load)
    if load < 1.0:
        raise InvalidInputError(
            "costs.wage_load is a multiplier (1.30 means +30%) and must be >= 1; "
            f"got {costs.wage_load!r}"
        )
    return headcount * wage * (1.0 + v.shock("scenario.wage_shock", wage_shock)) * load


def annualized_components(costs: CostInputs, scenario: Scenario) -> dict[str, float]:
    """Return annualized USD by component for one scenario."""
    kwh = v.non_negative("costs.kwh_per_year", costs.kwh_per_year)
    energy_rate = v.non_negative("costs.energy_rate_kwh", costs.energy_rate_kwh)
    demand_kw = v.non_negative("costs.demand_kw", costs.demand_kw)
    demand_rate = v.non_negative("costs.demand_rate_kw", costs.demand_rate_kw)
    capex_total = v.non_negative("costs.capex_total", costs.capex_total)
    capex_years = v.positive("costs.capex_years", costs.capex_years)

    return {
        "lease": annual_lease(costs, scenario.rent_shock),
        "labor": annual_labor(costs, scenario.wage_shock),
        "utilities": kwh * energy_rate + demand_kw * demand_rate * MONTHS_PER_YEAR,
        "property_tax": v.non_negative("costs.property_tax_annual", costs.property_tax_annual),
        "capex": capex_total / capex_years,
        "other_opex": v.non_negative("costs.other_opex_annual", costs.other_opex_annual),
    }


def annualized_total(components: Mapping[str, float]) -> float:
    """Return the exact-rounded sum of non-negative component dollars."""
    if not components:
        raise InvalidInputError("components must not be empty")
    values = [v.non_negative(f"components[{name!r}]", usd) for name, usd in components.items()]
    return math.fsum(values)


def cost_per_delivery(components: Mapping[str, float], deliveries: float) -> float:
    """Return annualized total cost divided by annual deliveries."""
    count = v.finite("deliveries", deliveries)
    if count <= 0:
        raise ZeroDeliveriesError(count)
    return annualized_total(components) / count


def staffing_headcount(
    annual_deliveries: float, assumptions: Assumptions | ModelAssumptions
) -> float:
    """Return FTEs: ``max(min_headcount, deliveries / deliveries_per_fte)`` (assumption A4)."""
    staffing = parse_assumptions(assumptions).labor.staffing
    deliveries = v.non_negative("annual_deliveries", annual_deliveries)
    return max(staffing.min_headcount, deliveries / staffing.deliveries_per_fte)


def nnn_opex_load(
    base_load: float,
    *,
    reference_rate: float,
    local_rate: float,
    assessed_value_psf: float,
    rent_psf_year: float,
) -> float:
    """Return the NNN load after replacing the reference tax rate with ``local_rate``.

    ``base_load`` already includes tax at ``reference_rate``. The difference
    is ``assessed_value_psf × (local_rate − reference_rate) / rent_psf_year``.
    A zero annual rent cannot carry that difference, so the base load is
    returned. The result is never negative.
    """
    base = v.non_negative("opex_load", base_load)
    reference = v.non_negative("reference_rate", reference_rate)
    local = v.non_negative("local_rate", local_rate)
    assessed = v.non_negative("assessed_value_psf", assessed_value_psf)
    rent = v.non_negative("rent_psf_year", rent_psf_year)
    if rent == 0.0:
        return base
    return max(0.0, base + assessed * (local - reference) / rent)


def upfront_capex(
    assumptions: Assumptions | ModelAssumptions,
    sqft: float | None = None,
    *,
    fitout_index: float = 1.0,
) -> tuple[float, float]:
    """Return ``(improvements, equipment)`` upfront capex in USD.

    ``sqft`` defaults to ``facility.sqft``. ``fitout_index`` scales fit-out
    only. Equipment stays the national catalog price.
    """
    a = parse_assumptions(assumptions)
    area = a.facility.sqft if sqft is None else v.positive("sqft", sqft)
    index = v.positive("fitout_index", fitout_index)
    improvements = a.capex.fitout_psf * index * area * (1.0 + a.capex.soft_contingency)
    return improvements, a.capex.equipment_usd


def build_cost_inputs(
    assumptions: Assumptions | ModelAssumptions,
    *,
    rent_psf_month: float,
    wage_annual: float,
    energy_rate_kwh: float,
    demand_rate_kw: float,
    annual_deliveries: float,
    opex_load: float | None = None,
    fitout_index: float = 1.0,
    property_tax_rate: float | None = None,
) -> CostInputs:
    """Combine the assumptions table with resolved public inputs into :class:`CostInputs`.

    Omitted optional arguments keep the assumptions-file values, so an older
    caller (and the golden fixtures) is unchanged.
    """
    a = parse_assumptions(assumptions)
    sqft = a.facility.sqft
    rent = v.non_negative("rent_psf_month", rent_psf_month)
    wage = v.non_negative("wage_annual", wage_annual)
    load = a.facility.opex_load if opex_load is None else v.non_negative("opex_load", opex_load)
    index = v.positive("fitout_index", fitout_index)
    tax_rate = (
        a.property_tax.effective_rate
        if property_tax_rate is None
        else v.non_negative("property_tax_rate", property_tax_rate)
    )
    headcount = staffing_headcount(annual_deliveries, a)

    base_lease = rent * MONTHS_PER_YEAR * sqft * (1.0 + load)
    base_labor = headcount * wage * a.labor.wage_load
    other_opex = a.other_opex.pct_of_lease_and_labor * (base_lease + base_labor)

    return CostInputs(
        sqft=sqft,
        rent_psf_month=rent,
        opex_load=load,
        wage_annual=wage,
        wage_load=a.labor.wage_load,
        headcount=headcount,
        kwh_per_year=a.utilities.kwh_per_sqft_year * sqft,
        energy_rate_kwh=v.non_negative("energy_rate_kwh", energy_rate_kwh),
        demand_kw=a.utilities.peak_kw_per_sqft * sqft,
        demand_rate_kw=v.non_negative("demand_rate_kw", demand_rate_kw),
        property_tax_annual=(
            0.0
            if a.property_tax.included_in_nnn
            else a.property_tax.assessed_value_psf * sqft * tax_rate
        ),
        capex_total=math.fsum(upfront_capex(a, sqft, fitout_index=index)),
        capex_years=a.capex.life_years,
        other_opex_annual=other_opex,
    )
