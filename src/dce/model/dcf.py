"""Discounted cash flow for one candidate delivery center (ADR-0005).

Contract
--------
``run_dcf(costs, dcf, assumptions, *, steady_deliveries, scenario) -> DcfResult``
    Year-by-year cash flows, NPV, IRR, and simple and discounted payback for
    one benefit lens. ``costs`` is the year-1 :class:`CostInputs` from
    :func:`dce.model.costs.build_cost_inputs`; ``steady_deliveries`` is the
    steady-state annual volume from the catchment (or the demand fallback),
    before ``scenario.delivery_shock``.

``run_dcf_views(costs, assumptions, *, steady_deliveries, scenario, dcf=None) -> DcfViews``
    Both decision lenses on the same inputs: ``standalone`` (headline) and
    ``incremental`` (the check).

``build_dcf_inputs(assumptions, *, benefit_mode=None) -> DcfInputs``
    Base values from the ``dcf:``, ``capex:`` and ``seasonality:`` sections.

``npv(rate, cash_flows)``, ``irr(cash_flows)``, ``payback_years(cash_flows, rate=0.0)``
    Generic helpers. Cash flow ``i`` is at the end of year ``i``; index 0 is
    today and is not discounted.

Timeline
--------
Year 0 holds upfront capex (improvements + equipment) and pre-opening labor
(``preopen_months / 12`` of year-1 labor, expensed). Years ``1..horizon``
are operating years with end-of-year cash flows.

Deliveries in year ``t``: ``steady × ramp[t-1]`` while ``t <= len(ramp)``,
then ``steady × ramp[-1] × (1 + growth) ** (t - len(ramp))``, capped at
``capacity_cap_multiple × steady``. ``steady`` already carries
``scenario.delivery_shock``.

Operating cost in year ``t`` reuses :func:`dce.model.costs.annualized_components`
on a copy of ``costs`` with rent escalated by ``(1 + rent_escalation) **
(t-1)``, wage by wage inflation, energy and demand rates by utility
inflation, headcount from :func:`staffing_headcount` on that year's
deliveries, other opex recomputed from that year's unshocked lease + labor,
and ``capex_total = 0``: capex is year-0 cash, never an annual charge here.
Property tax stays flat. With ``ramp[0] == 1`` and ``steady_deliveries``
equal to the static estimate, year-1 opex equals the static annualized total
minus its ``capex`` component.

Benefit (pre-tax, per year)
    standalone     deliveries × (fee × (1 + fee_escalation) ** (t-1) − inbound_freight)
    incremental    constraint_share × (status-quo opex_t + expansion annuity)
                   + deliveries × peak_excess_share
                     × loaded wage per delivery × (overtime_multiplier − 1)
                   + uplift × deliveries × gp_per_vehicle
    gp_allocation  deliveries × gp_per_vehicle   (upper bound only)

    *Status-quo opex* is the same year's cost model with rent set to
    ``status_quo_rent_psf_month`` (escalated): the cost an existing center
    would bear to serve the volume by expanding. The *expansion annuity*
    spreads this project's improvements capex (fit-out + soft cost) over the
    horizon at the discount rate; equipment is left out because an existing
    center already has its chargers, IT, and lifts. The overtime term follows
    dcf_design.md §1 and sits outside ``constraint_share``:
    ``peak_excess_share`` is the share of annual deliveries above the average
    monthly rate (:func:`peak_excess_share`), which existing centers would
    otherwise work at the overtime premium. Loaded wage per delivery is
    ``wage × (1 + wage_shock) × wage_load / deliveries_per_fte``.

Tax (cash, negative = benefit absorbed by consolidated income)
    state   = state_rate × (EBITDA − state depreciation)
    federal = fed_rate × (EBITDA − federal depreciation − state)
    Federal takes ``fed_bonus`` of all capex in year 0 and depreciates the
    rest straight-line from year 1. State takes no bonus: improvements and
    equipment depreciate straight-line from year 1 over their state lives.
    Any basis left at the end of the horizon is written off in the final
    year (leasehold improvements revert at lease end).

Terminal value
    ``none`` → 0. ``renewal`` → ``FCF_N × (1 + g) / (rate − g)`` at year N,
    included in NPV only. IRR and payback use the explicit cash flows.

Pure. No I/O, no network, no LLM.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from dataclasses import dataclass

from dce.model import _validate as v
from dce.model.assumptions import (
    BENEFIT_MODES,
    TERMINAL_MODES,
    BenefitMode,
    ModelAssumptions,
    TerminalMode,
    parse_assumptions,
)
from dce.model.costs import (
    annual_labor,
    annual_lease,
    annualized_components,
    staffing_headcount,
    upfront_capex,
)
from dce.model.demand import apply_delivery_shock
from dce.model.errors import InvalidInputError
from dce.model.types import Assumptions, CostInputs, Scenario

_IRR_LOW = -0.99
_IRR_HIGH = 100.0
_IRR_TOLERANCE = 1e-10
_IRR_MAX_ITER = 500


@dataclass(frozen=True)
class DcfInputs:
    """Every DCF knob. Rates are fractions per year (0.136 means 13.6%)."""

    horizon_years: int
    ramp: tuple[float, ...]
    growth: float
    capacity_cap_multiple: float
    benefit_mode: BenefitMode
    fee_per_delivery: float
    fee_escalation: float
    inbound_freight: float
    gp_per_vehicle: float
    uplift: float
    constraint_share: float
    status_quo_rent_psf_month: float
    overtime_multiplier: float
    peak_excess_share: float
    fitout_psf: float
    soft_contingency: float
    equipment: float
    preopen_months: float
    rent_escalation: float
    wage_inflation: float
    utility_inflation: float
    wacc: float
    fed_rate: float
    state_rate: float
    fed_bonus: float
    fed_improvement_life: float
    fed_equipment_life: float
    state_improvement_life: float
    state_equipment_life: float
    terminal: TerminalMode
    terminal_g: float


@dataclass(frozen=True)
class DcfYear:
    """One row of the yearly cash-flow table. USD; year 0 is today."""

    year: int
    deliveries: float
    headcount: float
    benefit: float
    lease: float
    labor: float
    utilities: float
    property_tax: float
    other_opex: float
    opex: float
    ebitda: float
    capex: float
    fed_depreciation: float
    state_depreciation: float
    tax: float
    fcf: float
    discounted_fcf: float
    cumulative_fcf: float
    cumulative_discounted_fcf: float


@dataclass(frozen=True)
class DcfResult:
    """Cash-flow table and decision metrics for one benefit lens."""

    benefit_mode: BenefitMode
    discount_rate: float
    years: tuple[DcfYear, ...]
    npv: float
    irr: float | None
    simple_payback_years: float | None
    discounted_payback_years: float | None
    total_capex: float
    terminal_value: float


@dataclass(frozen=True)
class DcfViews:
    """The two lenses the app always shows side by side (ADR-0005)."""

    standalone: DcfResult
    incremental: DcfResult


# -- generic helpers -----------------------------------------------------------------


def npv(rate: float, cash_flows: Sequence[float]) -> float:
    """Return ``Σ cf_t / (1 + rate) ** t`` with ``t`` starting at 0."""
    r = v.shock("rate", rate)
    return math.fsum(v.finite("cash flow", cf) / (1.0 + r) ** t for t, cf in enumerate(cash_flows))


def irr(cash_flows: Sequence[float]) -> float | None:
    """Return the internal rate of return by bisection, or ``None``.

    ``None`` means NPV does not change sign between −99% and +10,000%
    (for example, a project that never earns its capex back).
    """
    flows = [v.finite("cash flow", cf) for cf in cash_flows]
    lo, hi = _IRR_LOW, _IRR_HIGH
    f_lo, f_hi = npv(lo, flows), npv(hi, flows)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None
    for _ in range(_IRR_MAX_ITER):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid, flows)
        if f_mid == 0.0 or (hi - lo) / 2.0 < _IRR_TOLERANCE:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def payback_years(cash_flows: Sequence[float], rate: float = 0.0) -> float | None:
    """Return years until cumulative (discounted) cash flow first reaches 0.

    Linear inside the crossing year. ``0.0`` if year 0 is already
    non-negative; ``None`` if the cumulative never reaches 0.
    """
    r = v.shock("rate", rate)
    cumulative = 0.0
    for t, cf in enumerate(cash_flows):
        flow = v.finite("cash flow", cf) / (1.0 + r) ** t
        previous = cumulative
        cumulative += flow
        if cumulative >= 0.0:
            if t == 0:
                return 0.0
            return (t - 1) + (-previous / flow)
    return None


def peak_excess_share(quarter_shares: Sequence[float], month_in_quarter: Sequence[float]) -> float:
    """Share of annual deliveries above the average monthly rate (1/12 per month)."""
    average = 1.0 / 12.0
    months = [q * m for q in quarter_shares for m in month_in_quarter]
    return math.fsum(max(0.0, share - average) for share in months)


def capital_recovery_factor(rate: float, years: int) -> float:
    """Return the level annual payment per $1 today over ``years`` at ``rate``."""
    r = v.shock("rate", rate)
    n = int(v.positive("years", years))
    if r == 0.0:
        return 1.0 / n
    return r / (1.0 - (1.0 + r) ** -n)


# -- inputs --------------------------------------------------------------------------


def build_dcf_inputs(
    assumptions: Assumptions | ModelAssumptions, *, benefit_mode: BenefitMode | None = None
) -> DcfInputs:
    """Return :class:`DcfInputs` from the base values of the assumptions table."""
    a = parse_assumptions(assumptions)
    d = a.dcf
    return DcfInputs(
        horizon_years=d.horizon_years,
        ramp=d.ramp,
        growth=d.growth,
        capacity_cap_multiple=d.capacity_cap_multiple,
        benefit_mode=d.benefit_mode if benefit_mode is None else benefit_mode,
        fee_per_delivery=d.fee_per_delivery,
        fee_escalation=d.fee_escalation,
        inbound_freight=d.inbound_freight,
        gp_per_vehicle=d.gp_per_vehicle,
        uplift=d.uplift,
        constraint_share=d.constraint_share,
        status_quo_rent_psf_month=d.status_quo_rent_psf_month,
        overtime_multiplier=d.overtime_multiplier,
        peak_excess_share=peak_excess_share(
            a.seasonality.quarter_shares, a.seasonality.month_in_quarter
        ),
        fitout_psf=a.capex.fitout_psf,
        soft_contingency=a.capex.soft_contingency,
        equipment=a.capex.equipment_usd,
        preopen_months=d.preopen_months,
        rent_escalation=d.rent_escalation,
        wage_inflation=d.wage_inflation,
        utility_inflation=d.utility_inflation,
        wacc=d.discount_rate,
        fed_rate=d.tax.fed_rate,
        state_rate=d.tax.state_rate,
        fed_bonus=d.tax.fed_bonus,
        fed_improvement_life=d.tax.fed_improvement_life,
        fed_equipment_life=d.tax.fed_equipment_life,
        state_improvement_life=d.tax.state_improvement_life,
        state_equipment_life=d.tax.state_equipment_life,
        terminal=d.terminal,
        terminal_g=d.terminal_growth,
    )


# -- the model -----------------------------------------------------------------------


def run_dcf(
    costs: CostInputs,
    dcf: DcfInputs,
    assumptions: Assumptions | ModelAssumptions,
    *,
    steady_deliveries: float,
    scenario: Scenario,
) -> DcfResult:
    """Return the cash-flow table and metrics for ``dcf.benefit_mode``."""
    a = parse_assumptions(assumptions)
    _check_inputs(dcf)
    horizon = dcf.horizon_years
    steady = apply_delivery_shock(v.non_negative("steady_deliveries", steady_deliveries), scenario)
    cap = dcf.capacity_cap_multiple * steady

    improvements, equipment = upfront_capex(
        dataclasses.replace(
            a,
            capex=dataclasses.replace(
                a.capex,
                fitout_psf=dcf.fitout_psf,
                soft_contingency=dcf.soft_contingency,
                equipment_usd=dcf.equipment,
            ),
        ),
        costs.sqft,
    )
    total_capex = improvements + equipment
    annuity = improvements * capital_recovery_factor(dcf.wacc, horizon)

    fed_dep = _depreciation(improvements * (1.0 - dcf.fed_bonus), dcf.fed_improvement_life, horizon)
    fed_eq = _depreciation(equipment * (1.0 - dcf.fed_bonus), dcf.fed_equipment_life, horizon)
    state_imp = _depreciation(improvements, dcf.state_improvement_life, horizon)
    state_eq = _depreciation(equipment, dcf.state_equipment_life, horizon)

    rows: list[_Row] = []
    for t in range(1, horizon + 1):
        deliveries = _deliveries(t, steady, cap, dcf)
        comps = _year_opex(costs, a, dcf, scenario, t, deliveries, costs.rent_psf_month)
        benefit = _benefit(costs, a, dcf, scenario, t, deliveries, annuity)
        rows.append(
            _Row(
                year=t,
                deliveries=deliveries,
                headcount=staffing_headcount(deliveries, a),
                benefit=benefit,
                comps=comps,
                capex=0.0,
                fed_dep=fed_dep[t - 1] + fed_eq[t - 1],
                state_dep=state_imp[t - 1] + state_eq[t - 1],
            )
        )

    preopen = dcf.preopen_months / 12.0 * rows[0].comps["labor"] if rows else 0.0
    year0 = _Row(
        year=0,
        deliveries=0.0,
        headcount=0.0,
        benefit=0.0,
        comps={
            "lease": 0.0,
            "labor": preopen,
            "utilities": 0.0,
            "property_tax": 0.0,
            "other_opex": 0.0,
        },
        capex=total_capex,
        fed_dep=dcf.fed_bonus * total_capex,
        state_dep=0.0,
    )

    years = _cash_flow_table([year0, *rows], dcf)
    flows = [y.fcf for y in years]
    terminal_value = 0.0
    if dcf.terminal == "renewal":
        terminal_value = flows[-1] * (1.0 + dcf.terminal_g) / (dcf.wacc - dcf.terminal_g)
    npv_value = npv(dcf.wacc, flows) + terminal_value / (1.0 + dcf.wacc) ** horizon

    return DcfResult(
        benefit_mode=dcf.benefit_mode,
        discount_rate=dcf.wacc,
        years=tuple(years),
        npv=npv_value,
        irr=irr(flows),
        simple_payback_years=payback_years(flows),
        discounted_payback_years=payback_years(flows, dcf.wacc),
        total_capex=total_capex,
        terminal_value=terminal_value,
    )


def run_dcf_views(
    costs: CostInputs,
    assumptions: Assumptions | ModelAssumptions,
    *,
    steady_deliveries: float,
    scenario: Scenario,
    dcf: DcfInputs | None = None,
) -> DcfViews:
    """Run the standalone (headline) and incremental (check) lenses on the same inputs."""
    a = parse_assumptions(assumptions)
    base = build_dcf_inputs(a) if dcf is None else dcf
    return DcfViews(
        standalone=run_dcf(
            costs,
            dataclasses.replace(base, benefit_mode="standalone"),
            a,
            steady_deliveries=steady_deliveries,
            scenario=scenario,
        ),
        incremental=run_dcf(
            costs,
            dataclasses.replace(base, benefit_mode="incremental"),
            a,
            steady_deliveries=steady_deliveries,
            scenario=scenario,
        ),
    )


# -- internals -----------------------------------------------------------------------


@dataclass(frozen=True)
class _Row:
    year: int
    deliveries: float
    headcount: float
    benefit: float
    comps: dict[str, float]
    capex: float
    fed_dep: float
    state_dep: float


def _check_inputs(dcf: DcfInputs) -> None:
    if isinstance(dcf.horizon_years, bool) or not isinstance(dcf.horizon_years, int):
        raise InvalidInputError("dcf.horizon_years must be a whole number of years")
    if dcf.horizon_years < 1:
        raise InvalidInputError(f"dcf.horizon_years must be >= 1; got {dcf.horizon_years!r}")
    if not dcf.ramp:
        raise InvalidInputError("dcf.ramp must have at least one year")
    for i, share in enumerate(dcf.ramp):
        v.non_negative(f"dcf.ramp[{i}]", share)
    if dcf.benefit_mode not in BENEFIT_MODES:
        raise InvalidInputError(f"dcf.benefit_mode must be one of {list(BENEFIT_MODES)}")
    if dcf.terminal not in TERMINAL_MODES:
        raise InvalidInputError(f"dcf.terminal must be one of {list(TERMINAL_MODES)}")
    v.shock("dcf.growth", dcf.growth)
    v.positive("dcf.capacity_cap_multiple", dcf.capacity_cap_multiple)
    v.non_negative("dcf.fee_per_delivery", dcf.fee_per_delivery)
    v.shock("dcf.fee_escalation", dcf.fee_escalation)
    v.non_negative("dcf.inbound_freight", dcf.inbound_freight)
    v.finite("dcf.gp_per_vehicle", dcf.gp_per_vehicle)
    for name in ("uplift", "constraint_share", "fed_rate", "state_rate", "fed_bonus"):
        value = v.non_negative(f"dcf.{name}", getattr(dcf, name))
        if value > 1.0:
            raise InvalidInputError(f"dcf.{name} is a fraction and must be <= 1; got {value!r}")
    v.non_negative("dcf.status_quo_rent_psf_month", dcf.status_quo_rent_psf_month)
    if v.finite("dcf.overtime_multiplier", dcf.overtime_multiplier) < 1.0:
        raise InvalidInputError("dcf.overtime_multiplier must be >= 1")
    v.non_negative("dcf.peak_excess_share", dcf.peak_excess_share)
    v.non_negative("dcf.fitout_psf", dcf.fitout_psf)
    v.non_negative("dcf.soft_contingency", dcf.soft_contingency)
    v.non_negative("dcf.equipment", dcf.equipment)
    v.non_negative("dcf.preopen_months", dcf.preopen_months)
    v.shock("dcf.rent_escalation", dcf.rent_escalation)
    v.shock("dcf.wage_inflation", dcf.wage_inflation)
    v.shock("dcf.utility_inflation", dcf.utility_inflation)
    v.positive("dcf.wacc", dcf.wacc)
    for name in (
        "fed_improvement_life",
        "fed_equipment_life",
        "state_improvement_life",
        "state_equipment_life",
    ):
        v.positive(f"dcf.{name}", getattr(dcf, name))
    g = v.finite("dcf.terminal_g", dcf.terminal_g)
    if dcf.terminal == "renewal" and g >= dcf.wacc:
        raise InvalidInputError(
            f"dcf.terminal_g ({g}) must be below dcf.wacc ({dcf.wacc}) for a renewal perpetuity"
        )


def _deliveries(t: int, steady: float, cap: float, dcf: DcfInputs) -> float:
    ramp_years = len(dcf.ramp)
    if t <= ramp_years:
        raw = steady * dcf.ramp[t - 1]
    else:
        raw = steady * dcf.ramp[-1] * (1.0 + dcf.growth) ** (t - ramp_years)
    return min(raw, cap)


def _year_costs(
    costs: CostInputs,
    a: ModelAssumptions,
    dcf: DcfInputs,
    t: int,
    deliveries: float,
    rent_psf_month: float,
) -> CostInputs:
    """Year-``t`` copy of ``costs``: escalated prices, that year's headcount, no capex."""
    rent_factor = (1.0 + dcf.rent_escalation) ** (t - 1)
    wage_factor = (1.0 + dcf.wage_inflation) ** (t - 1)
    utility_factor = (1.0 + dcf.utility_inflation) ** (t - 1)
    year = dataclasses.replace(
        costs,
        rent_psf_month=rent_psf_month * rent_factor,
        wage_annual=costs.wage_annual * wage_factor,
        headcount=staffing_headcount(deliveries, a),
        energy_rate_kwh=costs.energy_rate_kwh * utility_factor,
        demand_rate_kw=costs.demand_rate_kw * utility_factor,
        capex_total=0.0,
    )
    other = a.other_opex.pct_of_lease_and_labor * (annual_lease(year) + annual_labor(year))
    return dataclasses.replace(year, other_opex_annual=other)


def _year_opex(
    costs: CostInputs,
    a: ModelAssumptions,
    dcf: DcfInputs,
    scenario: Scenario,
    t: int,
    deliveries: float,
    rent_psf_month: float,
) -> dict[str, float]:
    year = _year_costs(costs, a, dcf, t, deliveries, rent_psf_month)
    comps = annualized_components(year, scenario)
    del comps["capex"]  # capex is year-0 cash in the DCF
    return comps


def _benefit(
    costs: CostInputs,
    a: ModelAssumptions,
    dcf: DcfInputs,
    scenario: Scenario,
    t: int,
    deliveries: float,
    annuity: float,
) -> float:
    if dcf.benefit_mode == "standalone":
        fee = dcf.fee_per_delivery * (1.0 + dcf.fee_escalation) ** (t - 1)
        return deliveries * (fee - dcf.inbound_freight)
    if dcf.benefit_mode == "gp_allocation":
        return deliveries * dcf.gp_per_vehicle

    status_quo = math.fsum(
        _year_opex(costs, a, dcf, scenario, t, deliveries, dcf.status_quo_rent_psf_month).values()
    )
    wage_factor = (1.0 + dcf.wage_inflation) ** (t - 1)
    loaded_wage = costs.wage_annual * wage_factor * (1.0 + scenario.wage_shock) * costs.wage_load
    labor_per_delivery = loaded_wage / a.labor.staffing.deliveries_per_fte
    overtime = (
        deliveries * dcf.peak_excess_share * labor_per_delivery * (dcf.overtime_multiplier - 1.0)
    )
    uplift = dcf.uplift * deliveries * dcf.gp_per_vehicle
    return dcf.constraint_share * (status_quo + annuity) + overtime + uplift


def _depreciation(basis: float, life: float, horizon: int) -> list[float]:
    """Straight-line from year 1; the remaining basis is written off in the final year."""
    out: list[float] = []
    remaining = basis
    for t in range(1, horizon + 1):
        amount = remaining if t == horizon else min(remaining, basis / life)
        remaining -= amount
        out.append(amount)
    return out


def _cash_flow_table(rows: list[_Row], dcf: DcfInputs) -> list[DcfYear]:
    years: list[DcfYear] = []
    cumulative = 0.0
    cumulative_discounted = 0.0
    for row in rows:
        opex = math.fsum(row.comps.values())
        ebitda = row.benefit - opex
        state_tax = dcf.state_rate * (ebitda - row.state_dep)
        fed_tax = dcf.fed_rate * (ebitda - row.fed_dep - state_tax)
        tax = state_tax + fed_tax
        fcf = ebitda - row.capex - tax
        discounted = fcf / (1.0 + dcf.wacc) ** row.year
        cumulative += fcf
        cumulative_discounted += discounted
        years.append(
            DcfYear(
                year=row.year,
                deliveries=row.deliveries,
                headcount=row.headcount,
                benefit=row.benefit,
                lease=row.comps["lease"],
                labor=row.comps["labor"],
                utilities=row.comps["utilities"],
                property_tax=row.comps["property_tax"],
                other_opex=row.comps["other_opex"],
                opex=opex,
                ebitda=ebitda,
                capex=row.capex,
                fed_depreciation=row.fed_dep,
                state_depreciation=row.state_dep,
                tax=tax,
                fcf=fcf,
                discounted_fcf=discounted,
                cumulative_fcf=cumulative,
                cumulative_discounted_fcf=cumulative_discounted,
            )
        )
    return years
