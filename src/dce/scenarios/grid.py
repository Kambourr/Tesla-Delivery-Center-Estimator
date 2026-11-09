"""Scenario grid: wage, vehicle mix, DCF shocks, and low / base / high outcomes.

Contract
--------
``expand_default_scenarios(base_mix, assumptions) -> list[NamedScenario]``
    The M4 grid: ``baseline``, ``wage_minus_20``, ``wage_plus_20``,
    ``alt_mix``, ``wacc_low`` / ``wacc_high`` (the ``dcf.discount_rate``
    range ends, 9.7% / 16.3%), and ``growth_low`` / ``growth_high`` (the
    ``dcf.volume.growth`` ends, 0% / 10%).

``outcome_scenarios(assumptions, base_mix=None) -> list[NamedScenario]``
    ``low``, ``base``, ``high``. ``low`` is the bad outcome and ``high`` the
    good one, so each driver takes whichever range end hurts (or helps) NPV:

    ===========  ================================  =====  =================================
    driver       low (bad)                         base   high (good)
    ===========  ================================  =====  =================================
    deliveries   (3,000 / 4,500) × (1.00 / 1.10)   0      (6,500 / 4,500) × (1.30 / 1.10)
    rent         2.95 / 2.14 = +37.9%              0      1.74 / 2.14 = −18.7%
    wage         31.09 / 25.91 = +20%              0      20.73 / 25.91 = −20%
    fee          $1,250                            1,390  $1,640
    WACC         16.3%                             13.6%  9.7%
    horizon      8 years                           10     10 years (the lease)
    ===========  ================================  =====  =================================

    Deliveries, rent, and wage are ratios to the range base, applied as
    ``Scenario`` shocks, so they scale the catchment volume, the resolved
    rent, and the resolved wage of whatever ZIP is being estimated. The
    delivery ratio stays a fraction of that ZIP's own volume. It is composed
    with the handover factor (1.00 / 1.10 / 1.30) because the catchment
    volume is already at the base factor, 1.10. The low case keeps its bad
    rent, wage, fee, WACC, and 8-year horizon. Fee, WACC, and horizon are
    absolute :class:`DcfShocks`. The high horizon is the lease term.

``run_scenario_grid(geo, steady_deliveries, costs, scenarios, assumptions, *, catchment=None)``
    One :class:`ScenarioResult` per scenario, in input order. Each result is
    the same shape as ``dce.orchestrator.estimate``: static ``$/delivery`` at
    the shocked volume and both DCF views. ``steady_deliveries`` is the
    unshocked catchment volume (gravity base). ``costs`` supplies the
    resolved prices (rent, wage, energy and demand rates) and the facility;
    headcount and other opex are recomputed for each scenario's volume.

Pure: no file I/O, no SQLite, no network, no GUI, no LLM.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence

from dce.model import _validate as v
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import (
    annual_labor,
    annual_lease,
    annualized_components,
    annualized_total,
    cost_per_delivery,
    staffing_headcount,
)
from dce.model.dcf import DcfInputs, build_dcf_inputs, run_dcf_views
from dce.model.demand import apply_delivery_shock
from dce.model.drivers import top_drivers
from dce.model.errors import InvalidInputError
from dce.model.types import (
    Assumptions,
    CatchmentSummary,
    CostInputs,
    EstimateResult,
    GeoContext,
    InputProvenance,
    NearbyCenter,
    Scenario,
)
from dce.scenarios import ranges as r
from dce.scenarios.types import DcfShocks, NamedScenario, ScenarioResult

#: The M4 wage shock, ±20% (the labor.fallback_wage_hourly range is also ±20%).
WAGE_SHOCK = 0.20

_MIX_TOLERANCE = 1e-6


def compose_shocks(*shocks: float) -> float:
    """Return the single fractional shock equal to applying each in turn."""
    factor = 1.0
    for shock in shocks:
        factor *= 1.0 + v.shock("shock", shock)
    return factor - 1.0


def apply_dcf_shocks(dcf: DcfInputs, shocks: DcfShocks) -> DcfInputs:
    """Return ``dcf`` with every non-``None`` field of ``shocks`` replaced."""
    changes: dict[str, object] = {}
    if shocks.discount_rate is not None:
        changes["wacc"] = v.positive("dcf.discount_rate", shocks.discount_rate)
    if shocks.horizon_years is not None:
        horizon = shocks.horizon_years
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise InvalidInputError(
                f"dcf.horizon_years must be a whole number >= 1; got {horizon!r}"
            )
        changes["horizon_years"] = horizon
    if shocks.growth is not None:
        changes["growth"] = v.shock("dcf.growth", shocks.growth)
    if shocks.fee_per_delivery is not None:
        changes["fee_per_delivery"] = v.non_negative(
            "dcf.fee_per_delivery", shocks.fee_per_delivery
        )
    return dataclasses.replace(dcf, **changes)  # type: ignore[arg-type]


def alternate_mix(base_mix: Mapping[str, float]) -> dict[str, float]:
    """Return ``base_mix`` with its two largest shares swapped (ties by name).

    With the default 70 / 27 / 3 mix that is a Model 3-heavy 27 / 70 / 3.
    ``vehicle_mix`` does not move M3 cost math yet; the case is carried so
    the grid, the CLI, and the app already have it.
    """
    mix = _check_mix(base_mix)
    if len(mix) < 2:
        raise InvalidInputError("vehicle_mix needs at least two models for an alternate mix")
    first, second = sorted(mix, key=lambda name: (-mix[name], name))[:2]
    out = dict(mix)
    out[first], out[second] = mix[second], mix[first]
    return out


def expand_default_scenarios(
    base_mix: Mapping[str, float], assumptions: Assumptions | ModelAssumptions
) -> list[NamedScenario]:
    """Return the default M4 grid (see the module docstring)."""
    a = parse_assumptions(assumptions)
    mix = _check_mix(base_mix)
    wacc = r.require(a.ranges, r.DISCOUNT_RATE)
    growth = r.require(a.ranges, r.GROWTH)
    return [
        NamedScenario("baseline", "Baseline", _scenario(mix)),
        NamedScenario("wage_minus_20", "Wage −20%", _scenario(mix, wage_shock=-WAGE_SHOCK)),
        NamedScenario("wage_plus_20", "Wage +20%", _scenario(mix, wage_shock=WAGE_SHOCK)),
        NamedScenario("alt_mix", "Alternate vehicle mix", _scenario(alternate_mix(mix))),
        NamedScenario(
            "wacc_low",
            f"WACC {_pct(wacc.low)}",
            _scenario(mix),
            DcfShocks(discount_rate=wacc.low),
        ),
        NamedScenario(
            "wacc_high",
            f"WACC {_pct(wacc.high)}",
            _scenario(mix),
            DcfShocks(discount_rate=wacc.high),
        ),
        NamedScenario(
            "growth_low",
            f"Growth {_pct(growth.low)}",
            _scenario(mix),
            DcfShocks(growth=growth.low),
        ),
        NamedScenario(
            "growth_high",
            f"Growth {_pct(growth.high)}",
            _scenario(mix),
            DcfShocks(growth=growth.high),
        ),
    ]


def outcome_scenarios(
    assumptions: Assumptions | ModelAssumptions,
    base_mix: Mapping[str, float] | None = None,
) -> list[NamedScenario]:
    """Return ``low`` (bad outcome), ``base``, and ``high`` (good outcome)."""
    a = parse_assumptions(assumptions)
    mix = _check_mix(a.vehicle_mix if base_mix is None else base_mix)
    deliveries = r.require(a.ranges, r.DELIVERIES)
    handover = r.require(a.ranges, r.HANDOVER)
    wage = r.require(a.ranges, r.WAGE)
    fee = r.require(a.ranges, r.FEE)
    wacc = r.require(a.ranges, r.DISCOUNT_RATE)
    horizon = r.require(a.ranges, r.HORIZON)
    rent = r.rent_ratio(a.ranges)

    low = NamedScenario(
        "low",
        "Low (bad outcome)",
        _scenario(
            mix,
            wage_shock=r.ratio_shock(wage, wage.high),
            rent_shock=r.ratio_shock(rent, rent.high),
            delivery_shock=_delivery_case_shock(deliveries, deliveries.low, handover, handover.low),
        ),
        DcfShocks(
            discount_rate=wacc.high,
            horizon_years=_whole_years(horizon.low),
            fee_per_delivery=fee.low,
        ),
    )
    base = NamedScenario(
        "base",
        "Base",
        _scenario(mix),
        DcfShocks(
            discount_rate=wacc.base,
            horizon_years=_whole_years(horizon.base),
            fee_per_delivery=fee.base,
        ),
    )
    high = NamedScenario(
        "high",
        "High (good outcome)",
        _scenario(
            mix,
            wage_shock=r.ratio_shock(wage, wage.low),
            rent_shock=r.ratio_shock(rent, rent.low),
            delivery_shock=_delivery_case_shock(
                deliveries, deliveries.high, handover, handover.high
            ),
        ),
        DcfShocks(
            discount_rate=wacc.low,
            horizon_years=_whole_years(horizon.high),
            fee_per_delivery=fee.high,
        ),
    )
    return [low, base, high]


def costs_at(
    costs: CostInputs, assumptions: Assumptions | ModelAssumptions, deliveries: float
) -> CostInputs:
    """Return ``costs`` with headcount and other opex recomputed for ``deliveries``.

    Same formulas as :func:`dce.model.costs.build_cost_inputs`: headcount is
    :func:`staffing_headcount`, other opex is a share of unshocked lease + labor.
    """
    a = parse_assumptions(assumptions)
    staffed = dataclasses.replace(costs, headcount=staffing_headcount(deliveries, a))
    other = a.other_opex.pct_of_lease_and_labor * (annual_lease(staffed) + annual_labor(staffed))
    return dataclasses.replace(staffed, other_opex_annual=other)


def run_scenario(
    geo: GeoContext,
    steady_deliveries: float,
    costs: CostInputs,
    named: NamedScenario,
    assumptions: Assumptions | ModelAssumptions,
    *,
    catchment: CatchmentSummary | None = None,
    provenance: tuple[InputProvenance, ...] = (),
    nearby_centers: tuple[NearbyCenter, ...] = (),
) -> ScenarioResult:
    """Evaluate one scenario the way ``estimate(zip)`` evaluates its baseline."""
    a = parse_assumptions(assumptions)
    steady = v.non_negative("steady_deliveries", steady_deliveries)
    scenario = named.scenario
    shocked = apply_delivery_shock(steady, scenario)
    year1 = costs_at(costs, a, shocked)
    components = annualized_components(year1, scenario)
    dcf = apply_dcf_shocks(build_dcf_inputs(a), named.dcf)
    result = EstimateResult(
        geo=geo,
        scenario=scenario,
        cost_per_delivery=cost_per_delivery(components, shocked),
        annualized_total_cost=annualized_total(components),
        estimated_annual_deliveries=shocked,
        components=components,
        drivers=top_drivers(components),
        map_path=None,
        catchment=catchment,
        dcf=run_dcf_views(year1, a, steady_deliveries=steady, scenario=scenario, dcf=dcf),
        provenance=provenance,
        nearby_centers=nearby_centers,
    )
    return ScenarioResult(named=named, result=result)


def run_scenario_grid(
    geo: GeoContext,
    steady_deliveries: float,
    costs: CostInputs,
    scenarios: Sequence[NamedScenario],
    assumptions: Assumptions | ModelAssumptions,
    *,
    catchment: CatchmentSummary | None = None,
    provenance: tuple[InputProvenance, ...] = (),
    nearby_centers: tuple[NearbyCenter, ...] = (),
) -> list[ScenarioResult]:
    """Evaluate every scenario in order. Scenario ids must be unique."""
    ids = [named.scenario_id for named in scenarios]
    duplicates = sorted({sid for sid in ids if ids.count(sid) > 1})
    if duplicates:
        raise InvalidInputError(f"scenario ids must be unique; repeated: {duplicates}")
    a = parse_assumptions(assumptions)
    return [
        run_scenario(
            geo,
            steady_deliveries,
            costs,
            named,
            a,
            catchment=catchment,
            provenance=provenance,
            nearby_centers=nearby_centers,
        )
        for named in scenarios
    ]


# -- internals -----------------------------------------------------------------------


def _delivery_case_shock(
    deliveries: r.ValueRange,
    volume_end: float,
    handover: r.ValueRange,
    handover_end: float,
) -> float:
    """Return the shock that scales one ZIP's volume, then its handover factor.

    The catchment volume is already at the base handover factor, so the
    second ratio moves that volume from base H to the case's H. Both pieces
    are ratios of the ZIP's own volume, not a national delivery count.
    """
    return compose_shocks(
        r.ratio_shock(deliveries, volume_end),
        r.ratio_shock(handover, handover_end),
    )


def _scenario(
    mix: Mapping[str, float],
    *,
    wage_shock: float = 0.0,
    rent_shock: float = 0.0,
    delivery_shock: float = 0.0,
) -> Scenario:
    return Scenario(
        vehicle_mix=dict(mix),
        wage_shock=wage_shock,
        rent_shock=rent_shock,
        delivery_shock=delivery_shock,
    )


def _check_mix(mix: Mapping[str, float]) -> dict[str, float]:
    out = {
        str(name): v.non_negative(f"vehicle_mix[{name!r}]", share) for name, share in mix.items()
    }
    if not out:
        raise InvalidInputError("vehicle_mix must not be empty")
    total = math.fsum(out.values())
    if abs(total - 1.0) > _MIX_TOLERANCE:
        raise InvalidInputError(f"vehicle_mix shares must sum to 1; got {total!r}")
    return out


def _whole_years(value: float) -> int:
    years = round(v.positive("dcf.horizon_years", value))
    if years < 1 or not math.isclose(years, value):
        raise InvalidInputError(f"dcf.horizon_years range must hold whole years; got {value!r}")
    return int(years)


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%".replace(".0%", "%")


__all__ = [
    "WAGE_SHOCK",
    "alternate_mix",
    "apply_dcf_shocks",
    "compose_shocks",
    "costs_at",
    "expand_default_scenarios",
    "outcome_scenarios",
    "run_scenario",
    "run_scenario_grid",
]
