"""NPV tornado: one-at-a-time sensitivity of DCF NPV to each driver.

Contract
--------
``dcf_tornado(base_inputs, ranges=None) -> list[TornadoBar]``
    For each driver, run :func:`dce.model.dcf.run_dcf` twice, once at the low
    end and once at the high end of its range, holding every other input at
    base. Bars are sorted by ``swing`` (largest first; ties by driver id).
    ``ranges`` defaults to ``ModelAssumptions.ranges``; rent uses the
    research ratios in :mod:`dce.scenarios.ranges` unless ``ranges`` carries
    ``facility.rent_multiplier``.

``tornado_rows(bars) -> list[dict[str, str | float]]``
    The same bars as JSON- and CSV-ready dicts for the app or CLI. Charting
    needs nothing beyond these numbers (no matplotlib here).

Drivers
-------
Ratio drivers scale what the caller resolved: ``deliveries`` scales
``steady_deliveries`` by ``end / base`` of ``demand.base_annual_deliveries``
(3,000 / 4,500 and 6,500 / 4,500), ``wage`` scales the resolved wage by
``labor.fallback_wage_hourly`` (±20%), and ``rent`` scales the resolved rent
by the research ratios. Every other driver replaces the input with the range
end: fee, inbound freight, deliveries per FTE, minimum headcount, wage load,
WACC, horizon, growth, ramp, fit-out, equipment, rent escalation, and wage
inflation. The ``incremental`` lens adds constraint share, uplift, and GP per
vehicle (they do not enter standalone NPV).

Pure. No I/O.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from dce.model.assumptions import BenefitMode, ModelAssumptions, ValueRange, parse_assumptions
from dce.model.dcf import DcfInputs, build_dcf_inputs, run_dcf
from dce.model.types import Assumptions, CostInputs, Scenario
from dce.scenarios import ranges as r
from dce.scenarios.grid import compose_shocks, costs_at
from dce.scenarios.types import TornadoBar


@dataclass(frozen=True)
class TornadoInputs:
    """The base case the tornado perturbs. Same inputs ``run_dcf`` takes.

    ``dcf`` defaults to :func:`build_dcf_inputs` on ``assumptions``.
    ``benefit_mode`` picks the lens whose NPV is measured.
    """

    costs: CostInputs
    assumptions: Assumptions | ModelAssumptions
    steady_deliveries: float
    scenario: Scenario
    dcf: DcfInputs | None = None
    benefit_mode: BenefitMode = "standalone"


@dataclass(frozen=True)
class _Case:
    costs: CostInputs
    a: ModelAssumptions
    steady: float
    scenario: Scenario
    dcf: DcfInputs


# end -> (perturbed case, displayed input value)
_Apply = Callable[[_Case, float], _Case]


@dataclass(frozen=True)
class _Driver:
    driver: str
    label: str
    unit: str
    low: float
    high: float
    base_input: float
    apply: _Apply
    display: Callable[[float], float]


def dcf_tornado(
    base_inputs: TornadoInputs, ranges: Mapping[str, ValueRange] | None = None
) -> list[TornadoBar]:
    """Return one bar per driver, sorted by NPV swing, largest first."""
    a = parse_assumptions(base_inputs.assumptions)
    rng = a.ranges if ranges is None else ranges
    dcf = build_dcf_inputs(a) if base_inputs.dcf is None else base_inputs.dcf
    base = _Case(
        costs=base_inputs.costs,
        a=a,
        steady=base_inputs.steady_deliveries,
        scenario=base_inputs.scenario,
        dcf=dataclasses.replace(dcf, benefit_mode=base_inputs.benefit_mode),
    )
    npv_base = _npv(base)
    bars = [_bar(d, base, npv_base) for d in _drivers(base, rng, base_inputs.benefit_mode)]
    return sorted(bars, key=lambda bar: (-bar.swing, bar.driver))


def tornado_rows(bars: Sequence[TornadoBar]) -> list[dict[str, str | float]]:
    """Return ``bars`` as plain dicts, in order."""
    return [dataclasses.asdict(bar) for bar in bars]


# -- internals -----------------------------------------------------------------------


def _npv(case: _Case) -> float:
    return run_dcf(
        case.costs,
        case.dcf,
        case.a,
        steady_deliveries=case.steady,
        scenario=case.scenario,
    ).npv


def _bar(d: _Driver, base: _Case, npv_base: float) -> TornadoBar:
    npv_at_low = _npv(d.apply(base, d.low))
    npv_at_high = _npv(d.apply(base, d.high))
    if npv_at_low <= npv_at_high:
        lo_input, lo_npv, hi_input, hi_npv = d.low, npv_at_low, d.high, npv_at_high
    else:
        lo_input, lo_npv, hi_input, hi_npv = d.high, npv_at_high, d.low, npv_at_low
    return TornadoBar(
        driver=d.driver,
        label=d.label,
        unit=d.unit,
        input_base=d.base_input,
        input_at_npv_low=d.display(lo_input),
        input_at_npv_high=d.display(hi_input),
        npv_low=lo_npv,
        npv_base=npv_base,
        npv_high=hi_npv,
        swing=hi_npv - lo_npv,
    )


def _dcf_field(name: str) -> _Apply:
    def apply(case: _Case, end: float) -> _Case:
        changes: dict[str, object] = {name: int(round(end)) if name == "horizon_years" else end}
        dcf = dataclasses.replace(case.dcf, **changes)  # type: ignore[arg-type]
        return dataclasses.replace(case, dcf=dcf)

    return apply


def _staffing_field(name: str) -> _Apply:
    def apply(case: _Case, end: float) -> _Case:
        staffing = dataclasses.replace(case.a.labor.staffing, **{name: end})
        a = dataclasses.replace(case.a, labor=dataclasses.replace(case.a.labor, staffing=staffing))
        return dataclasses.replace(case, a=a, costs=costs_at(case.costs, a, case.steady))

    return apply


def _ratio_driver(
    driver: str,
    label: str,
    unit: str,
    rng: ValueRange,
    base_input: float,
    shock_field: str,
) -> _Driver:
    def apply(case: _Case, end: float) -> _Case:
        current = getattr(case.scenario, shock_field)
        changes: dict[str, object] = {shock_field: compose_shocks(current, r.ratio_shock(rng, end))}
        scenario = dataclasses.replace(case.scenario, **changes)  # type: ignore[arg-type]
        return dataclasses.replace(case, scenario=scenario)

    return _Driver(
        driver=driver,
        label=label,
        unit=unit,
        low=rng.low,
        high=rng.high,
        base_input=base_input,
        apply=apply,
        display=lambda end: base_input * end / rng.base,
    )


def _value_driver(
    driver: str,
    label: str,
    unit: str,
    rng: ValueRange,
    base_input: float,
    apply: _Apply,
) -> _Driver:
    return _Driver(
        driver=driver,
        label=label,
        unit=unit,
        low=rng.low,
        high=rng.high,
        base_input=base_input,
        apply=apply,
        display=lambda end: end,
    )


def _ramp_driver(case: _Case) -> _Driver:
    ramps = {0.0: case.a.dcf.ramp_low, 1.0: case.a.dcf.ramp_high}

    def apply(c: _Case, end: float) -> _Case:
        return dataclasses.replace(c, dcf=dataclasses.replace(c.dcf, ramp=ramps[end]))

    first = {0.0: case.a.dcf.ramp_low[0], 1.0: case.a.dcf.ramp_high[0]}
    return _Driver(
        driver="ramp",
        label="Ramp (year-1 share of steady volume)",
        unit="fraction",
        low=0.0,
        high=1.0,
        base_input=case.dcf.ramp[0],
        apply=apply,
        display=lambda end: first[end],
    )


def _wage_load(case: _Case, end: float) -> _Case:
    costs = costs_at(dataclasses.replace(case.costs, wage_load=end), case.a, case.steady)
    return dataclasses.replace(case, costs=costs)


def _drivers(
    case: _Case, rng: Mapping[str, ValueRange], benefit_mode: BenefitMode
) -> list[_Driver]:
    d = case.dcf
    steady = case.steady * (1.0 + case.scenario.delivery_shock)
    hourly = (
        case.costs.wage_annual / case.a.labor.paid_hours_per_fte * (1.0 + case.scenario.wage_shock)
    )
    rent = case.costs.rent_psf_month * (1.0 + case.scenario.rent_shock)
    staffing = case.a.labor.staffing
    get = r.require
    drivers = [
        _ratio_driver(
            "deliveries",
            "Deliveries",
            "deliveries/yr",
            get(rng, r.DELIVERIES),
            steady,
            "delivery_shock",
        ),
        _ratio_driver("wage", "Wage", "USD/h", get(rng, r.WAGE), hourly, "wage_shock"),
        _ratio_driver("rent", "Rent", "USD/sf/mo", r.rent_ratio(rng), rent, "rent_shock"),
        _value_driver(
            "fee",
            "Fee per delivery",
            "USD",
            get(rng, r.FEE),
            d.fee_per_delivery,
            _dcf_field("fee_per_delivery"),
        ),
        _value_driver(
            "inbound_freight",
            "Inbound freight",
            "USD/car",
            get(rng, r.FREIGHT),
            d.inbound_freight,
            _dcf_field("inbound_freight"),
        ),
        _value_driver(
            "deliveries_per_fte",
            "Deliveries per FTE",
            "deliveries/FTE",
            get(rng, r.DELIVERIES_PER_FTE),
            staffing.deliveries_per_fte,
            _staffing_field("deliveries_per_fte"),
        ),
        _value_driver(
            "min_headcount",
            "Minimum headcount",
            "FTE",
            get(rng, r.MIN_HEADCOUNT),
            staffing.min_headcount,
            _staffing_field("min_headcount"),
        ),
        _value_driver(
            "wage_load",
            "Wage load",
            "multiplier",
            get(rng, r.WAGE_LOAD),
            case.costs.wage_load,
            _wage_load,
        ),
        _value_driver(
            "wacc",
            "WACC",
            "rate",
            get(rng, r.DISCOUNT_RATE),
            d.wacc,
            _dcf_field("wacc"),
        ),
        _value_driver(
            "horizon",
            "Horizon",
            "years",
            get(rng, r.HORIZON),
            float(d.horizon_years),
            _dcf_field("horizon_years"),
        ),
        _value_driver(
            "growth",
            "Growth after ramp",
            "rate",
            get(rng, r.GROWTH),
            d.growth,
            _dcf_field("growth"),
        ),
        _ramp_driver(case),
        _value_driver(
            "fitout",
            "Fit-out",
            "USD/sf",
            get(rng, r.FITOUT),
            d.fitout_psf,
            _dcf_field("fitout_psf"),
        ),
        _value_driver(
            "equipment",
            "Equipment and IT",
            "USD",
            get(rng, r.EQUIPMENT),
            d.equipment,
            _dcf_field("equipment"),
        ),
        _value_driver(
            "rent_escalation",
            "Rent escalation",
            "rate",
            get(rng, r.RENT_ESCALATION),
            d.rent_escalation,
            _dcf_field("rent_escalation"),
        ),
        _value_driver(
            "wage_inflation",
            "Wage inflation",
            "rate",
            get(rng, r.WAGE_INFLATION),
            d.wage_inflation,
            _dcf_field("wage_inflation"),
        ),
    ]
    if benefit_mode != "standalone":
        drivers += [
            _value_driver(
                "gp_per_vehicle",
                "GP per vehicle",
                "USD",
                get(rng, r.GP_PER_VEHICLE),
                d.gp_per_vehicle,
                _dcf_field("gp_per_vehicle"),
            ),
        ]
    if benefit_mode == "incremental":
        drivers += [
            _value_driver(
                "constraint_share",
                "Capacity-constraint share",
                "fraction",
                get(rng, r.CONSTRAINT_SHARE),
                d.constraint_share,
                _dcf_field("constraint_share"),
            ),
            _value_driver(
                "uplift",
                "Proximity uplift",
                "fraction",
                get(rng, r.UPLIFT),
                d.uplift,
                _dcf_field("uplift"),
            ),
        ]
    return drivers


__all__ = ["TornadoInputs", "dcf_tornado", "tornado_rows"]
