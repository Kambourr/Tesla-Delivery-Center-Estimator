"""Typed view of the modeling assumptions table.

The default table ships as ``data/defaults/assumptions.yaml``. Reading that
file is I/O, so it happens outside the model (the orchestrator, or a test).
The caller passes the parsed mapping in; :func:`parse_assumptions` checks
its shape and returns frozen dataclasses. Pure: no file access here.

Parsing is strict. An unknown key, a missing key, a wrong type, or an
unsupported ``schema_version`` raises :class:`AssumptionsError`, so a typo
in the YAML fails loudly instead of silently using a default.

Ranges (schema 3)
-----------------
A numeric key may be either a plain number or a mapping with exactly
``low``, ``base`` and ``high`` (``low <= base <= high``, ordered by the input
value, not by its effect on cost or NPV). The typed field always holds the
``base`` value, so the model runs on base values. Every range is also kept
in :attr:`ModelAssumptions.ranges` under its dotted path (for example
``"dcf.discount_rate"``) for the M4 scenarios and the NPV tornado. Vector
inputs with ranges (the ramp and the within-quarter month split) carry their
``low``/``base``/``high`` tuples on their own dataclasses. Schema 3 adds
``demand.handover_factor`` (low 1.00 / base 1.10 / high 1.30) and
``demand.fallback_tesla_ev_share`` (the non-California Tesla share of EV
sales). Schema 2 is no longer accepted.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal, cast

from dce.model import _validate as v
from dce.model.errors import AssumptionsError, InvalidInputError
from dce.model.types import Assumptions

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({3})

BenefitMode = Literal["standalone", "incremental", "gp_allocation"]
TerminalMode = Literal["none", "renewal"]
BENEFIT_MODES: tuple[BenefitMode, ...] = ("standalone", "incremental", "gp_allocation")
TERMINAL_MODES: tuple[TerminalMode, ...] = ("none", "renewal")

# Shares that must sum to 1 may be off by float rounding in YAML.
_SUM_TOLERANCE = 1e-6
_SOC_PATTERN = re.compile(r"^\d{2}-\d{4}$")


@dataclass(frozen=True)
class ValueRange:
    """Low / base / high values for one numeric input, ordered by input value."""

    low: float
    base: float
    high: float


@dataclass(frozen=True)
class FacilityAssumptions:
    sqft: float
    opex_load: float
    catchment_miles: float


@dataclass(frozen=True)
class StaffingAssumptions:
    min_headcount: float
    deliveries_per_fte: float


@dataclass(frozen=True)
class WageMixEntry:
    """One delivery role: its BLS SOC code(s), a label, and its share of headcount."""

    socs: tuple[str, ...]
    title: str
    share: float


@dataclass(frozen=True)
class LaborAssumptions:
    wage_load: float
    paid_hours_per_fte: float
    fallback_wage_hourly: float
    staffing: StaffingAssumptions
    wage_mix: tuple[WageMixEntry, ...]


@dataclass(frozen=True)
class SeasonalityAssumptions:
    """Share of annual deliveries by quarter, and by month inside a quarter."""

    quarter_shares: tuple[float, float, float, float]
    month_in_quarter: tuple[float, float, float]
    month_in_quarter_low: tuple[float, float, float]
    month_in_quarter_high: tuple[float, float, float]


@dataclass(frozen=True)
class UtilityAssumptions:
    kwh_per_sqft_year: float
    peak_kw_per_sqft: float


@dataclass(frozen=True)
class PropertyTaxAssumptions:
    assessed_value_psf: float
    effective_rate: float
    included_in_nnn: bool


@dataclass(frozen=True)
class CapexAssumptions:
    fitout_psf: float
    soft_contingency: float
    equipment_usd: float
    life_years: float


@dataclass(frozen=True)
class OtherOpexAssumptions:
    pct_of_lease_and_labor: float


@dataclass(frozen=True)
class DemandFactor:
    """One demand driver: its value at the reference ("median") site and its elasticity."""

    reference: float
    elasticity: float


@dataclass(frozen=True)
class DemandAssumptions:
    base_annual_deliveries: float
    catchment_population: DemandFactor
    median_hh_income: DemandFactor
    ev_share: DemandFactor
    mean_commute: DemandFactor
    score_min: float
    score_max: float
    handover_factor: float
    fallback_tesla_ev_share: float


@dataclass(frozen=True)
class DcfTaxAssumptions:
    fed_rate: float
    state_rate: float
    fed_bonus: float
    fed_improvement_life: float
    fed_equipment_life: float
    state_improvement_life: float
    state_equipment_life: float


@dataclass(frozen=True)
class DcfAssumptions:
    horizon_years: int
    benefit_mode: BenefitMode
    ramp: tuple[float, ...]
    ramp_low: tuple[float, ...]
    ramp_high: tuple[float, ...]
    growth: float
    capacity_cap_multiple: float
    fee_per_delivery: float
    fee_escalation: float
    inbound_freight: float
    gp_per_vehicle: float
    constraint_share: float
    status_quo_rent_psf_month: float
    overtime_multiplier: float
    uplift: float
    preopen_months: float
    rent_escalation: float
    wage_inflation: float
    utility_inflation: float
    discount_rate: float
    tax: DcfTaxAssumptions
    terminal: TerminalMode
    terminal_growth: float


@dataclass(frozen=True)
class ModelAssumptions:
    schema_version: int
    assumptions_version: str
    as_of: str
    facility: FacilityAssumptions
    labor: LaborAssumptions
    vehicle_mix: dict[str, float]
    seasonality: SeasonalityAssumptions
    utilities: UtilityAssumptions
    property_tax: PropertyTaxAssumptions
    capex: CapexAssumptions
    other_opex: OtherOpexAssumptions
    demand: DemandAssumptions
    dcf: DcfAssumptions
    ranges: dict[str, ValueRange]


def parse_assumptions(raw: Assumptions | ModelAssumptions) -> ModelAssumptions:
    """Validate an assumptions mapping and return the typed view.

    A :class:`ModelAssumptions` passes through unchanged, so model functions
    accept either the raw mapping or an already parsed table.
    """
    if isinstance(raw, ModelAssumptions):
        return raw
    try:
        return _Parser().parse(raw)
    except AssumptionsError:
        raise
    except InvalidInputError as exc:
        raise AssumptionsError(str(exc)) from exc


Check = Callable[[str, float], float]


class _Parser:
    """Holds the ranges collected while parsing one table."""

    def __init__(self) -> None:
        self.ranges: dict[str, ValueRange] = {}

    # -- top level -----------------------------------------------------------------

    def parse(self, raw: Assumptions) -> ModelAssumptions:
        root = _section(raw, "assumptions")
        _exact_keys(
            "assumptions",
            root,
            {
                "schema_version",
                "assumptions_version",
                "as_of",
                "facility",
                "labor",
                "vehicle_mix",
                "seasonality",
                "utilities",
                "property_tax",
                "capex",
                "other_opex",
                "demand",
                "dcf",
            },
        )
        schema_version = root["schema_version"]
        if isinstance(schema_version, bool) or not isinstance(schema_version, int):
            raise AssumptionsError("assumptions.schema_version must be an integer")
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise AssumptionsError(
                f"assumptions.schema_version {schema_version} is not supported; "
                f"expected one of {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
            )

        return ModelAssumptions(
            schema_version=schema_version,
            assumptions_version=_text(root, "assumptions_version", "assumptions"),
            as_of=_text(root, "as_of", "assumptions"),
            facility=self._facility(root["facility"]),
            labor=self._labor(root["labor"]),
            vehicle_mix=_vehicle_mix(root["vehicle_mix"]),
            seasonality=_seasonality(root["seasonality"]),
            utilities=self._utilities(root["utilities"]),
            property_tax=self._property_tax(root["property_tax"]),
            capex=self._capex(root["capex"]),
            other_opex=self._other_opex(root["other_opex"]),
            demand=self._demand(root["demand"]),
            dcf=self._dcf(root["dcf"]),
            ranges=dict(self.ranges),
        )

    # -- sections ------------------------------------------------------------------

    def _facility(self, value: object) -> FacilityAssumptions:
        s = _section(value, "facility")
        _exact_keys("facility", s, {"sqft", "opex_load", "catchment_miles"})
        return FacilityAssumptions(
            sqft=self.num(s, "sqft", "facility", v.positive),
            opex_load=self.num(s, "opex_load", "facility", v.non_negative),
            catchment_miles=self.num(s, "catchment_miles", "facility", v.positive),
        )

    def _labor(self, value: object) -> LaborAssumptions:
        s = _section(value, "labor")
        _exact_keys(
            "labor",
            s,
            {"wage_load", "paid_hours_per_fte", "fallback_wage_hourly", "staffing", "wage_mix"},
        )
        staffing = _section(s["staffing"], "labor.staffing")
        _exact_keys("labor.staffing", staffing, {"min_headcount", "deliveries_per_fte"})
        return LaborAssumptions(
            wage_load=self.num(s, "wage_load", "labor", _wage_load),
            paid_hours_per_fte=self.num(s, "paid_hours_per_fte", "labor", v.positive),
            fallback_wage_hourly=self.num(s, "fallback_wage_hourly", "labor", v.positive),
            staffing=StaffingAssumptions(
                min_headcount=self.num(staffing, "min_headcount", "labor.staffing", v.non_negative),
                deliveries_per_fte=self.num(
                    staffing, "deliveries_per_fte", "labor.staffing", v.positive
                ),
            ),
            wage_mix=_wage_mix(s["wage_mix"]),
        )

    def _utilities(self, value: object) -> UtilityAssumptions:
        s = _section(value, "utilities")
        _exact_keys("utilities", s, {"kwh_per_sqft_year", "peak_kw_per_sqft"})
        return UtilityAssumptions(
            kwh_per_sqft_year=self.num(s, "kwh_per_sqft_year", "utilities", v.non_negative),
            peak_kw_per_sqft=self.num(s, "peak_kw_per_sqft", "utilities", v.non_negative),
        )

    def _property_tax(self, value: object) -> PropertyTaxAssumptions:
        s = _section(value, "property_tax")
        _exact_keys("property_tax", s, {"assessed_value_psf", "effective_rate", "included_in_nnn"})
        return PropertyTaxAssumptions(
            assessed_value_psf=self.num(s, "assessed_value_psf", "property_tax", v.non_negative),
            effective_rate=self.num(s, "effective_rate", "property_tax", v.non_negative),
            included_in_nnn=_bool(s, "included_in_nnn", "property_tax"),
        )

    def _capex(self, value: object) -> CapexAssumptions:
        s = _section(value, "capex")
        _exact_keys("capex", s, {"fitout_psf", "soft_contingency", "equipment_usd", "life_years"})
        return CapexAssumptions(
            fitout_psf=self.num(s, "fitout_psf", "capex", v.non_negative),
            soft_contingency=self.num(s, "soft_contingency", "capex", v.non_negative),
            equipment_usd=self.num(s, "equipment_usd", "capex", v.non_negative),
            life_years=self.num(s, "life_years", "capex", v.positive),
        )

    def _other_opex(self, value: object) -> OtherOpexAssumptions:
        s = _section(value, "other_opex")
        _exact_keys("other_opex", s, {"pct_of_lease_and_labor"})
        return OtherOpexAssumptions(
            pct_of_lease_and_labor=self.num(
                s, "pct_of_lease_and_labor", "other_opex", v.non_negative
            ),
        )

    def _demand(self, value: object) -> DemandAssumptions:
        s = _section(value, "demand")
        _exact_keys(
            "demand",
            s,
            {
                "base_annual_deliveries",
                "factors",
                "score_min",
                "score_max",
                "handover_factor",
                "fallback_tesla_ev_share",
            },
        )
        factors = _section(s["factors"], "demand.factors")
        _exact_keys(
            "demand.factors",
            factors,
            {"catchment_population", "median_hh_income", "ev_share", "mean_commute"},
        )
        score_min = self.num(s, "score_min", "demand", v.non_negative)
        score_max = self.num(s, "score_max", "demand", v.positive)
        if score_min > score_max:
            raise AssumptionsError(
                f"demand.score_min ({score_min}) must not exceed demand.score_max ({score_max})"
            )
        return DemandAssumptions(
            base_annual_deliveries=self.num(s, "base_annual_deliveries", "demand", v.positive),
            catchment_population=_factor(factors, "catchment_population"),
            median_hh_income=_factor(factors, "median_hh_income"),
            ev_share=_factor(factors, "ev_share"),
            mean_commute=_factor(factors, "mean_commute"),
            score_min=score_min,
            score_max=score_max,
            handover_factor=self.num(s, "handover_factor", "demand", v.positive),
            fallback_tesla_ev_share=self.num(s, "fallback_tesla_ev_share", "demand", _share),
        )

    def _dcf(self, value: object) -> DcfAssumptions:
        s = _section(value, "dcf")
        _exact_keys(
            "dcf",
            s,
            {
                "horizon_years",
                "benefit_mode",
                "volume",
                "standalone",
                "incremental",
                "gp_per_vehicle",
                "preopen_months",
                "escalation",
                "discount_rate",
                "tax",
                "terminal",
            },
        )
        volume = _section(s["volume"], "dcf.volume")
        _exact_keys("dcf.volume", volume, {"ramp", "growth", "capacity_cap_multiple"})
        ramp = _vector_range(volume, "ramp", "dcf.volume", length=None)

        standalone = _section(s["standalone"], "dcf.standalone")
        _exact_keys(
            "dcf.standalone", standalone, {"fee_per_delivery", "fee_escalation", "inbound_freight"}
        )
        incremental = _section(s["incremental"], "dcf.incremental")
        _exact_keys(
            "dcf.incremental",
            incremental,
            {"constraint_share", "status_quo_rent_psf_month", "overtime_multiplier", "uplift"},
        )
        escalation = _section(s["escalation"], "dcf.escalation")
        _exact_keys("dcf.escalation", escalation, {"rent", "wage", "utilities"})
        tax = _section(s["tax"], "dcf.tax")
        _exact_keys(
            "dcf.tax",
            tax,
            {
                "fed_rate",
                "state_rate",
                "fed_bonus",
                "fed_improvement_life",
                "fed_equipment_life",
                "state_improvement_life",
                "state_equipment_life",
            },
        )
        terminal = _section(s["terminal"], "dcf.terminal")
        _exact_keys("dcf.terminal", terminal, {"mode", "growth"})

        discount_rate = self.num(s, "discount_rate", "dcf", v.positive)
        terminal_growth = self.num(terminal, "growth", "dcf.terminal", v.finite)
        terminal_mode = cast(
            TerminalMode, _choice(terminal, "mode", "dcf.terminal", TERMINAL_MODES)
        )
        if terminal_mode == "renewal" and terminal_growth >= discount_rate:
            raise AssumptionsError(
                f"dcf.terminal.growth ({terminal_growth}) must be below dcf.discount_rate "
                f"({discount_rate}) for a renewal perpetuity"
            )

        return DcfAssumptions(
            horizon_years=self.integer(s, "horizon_years", "dcf"),
            benefit_mode=cast(BenefitMode, _choice(s, "benefit_mode", "dcf", BENEFIT_MODES)),
            ramp=ramp[1],
            ramp_low=ramp[0],
            ramp_high=ramp[2],
            growth=self.num(volume, "growth", "dcf.volume", _rate),
            capacity_cap_multiple=self.num(
                volume, "capacity_cap_multiple", "dcf.volume", v.positive
            ),
            fee_per_delivery=self.num(
                standalone, "fee_per_delivery", "dcf.standalone", v.non_negative
            ),
            fee_escalation=self.num(standalone, "fee_escalation", "dcf.standalone", _rate),
            inbound_freight=self.num(
                standalone, "inbound_freight", "dcf.standalone", v.non_negative
            ),
            gp_per_vehicle=self.num(s, "gp_per_vehicle", "dcf", v.finite),
            constraint_share=self.num(
                incremental, "constraint_share", "dcf.incremental", _fraction
            ),
            status_quo_rent_psf_month=self.num(
                incremental, "status_quo_rent_psf_month", "dcf.incremental", v.non_negative
            ),
            overtime_multiplier=self.num(
                incremental, "overtime_multiplier", "dcf.incremental", _at_least_one
            ),
            uplift=self.num(incremental, "uplift", "dcf.incremental", _fraction),
            preopen_months=self.num(s, "preopen_months", "dcf", v.non_negative),
            rent_escalation=self.num(escalation, "rent", "dcf.escalation", _rate),
            wage_inflation=self.num(escalation, "wage", "dcf.escalation", _rate),
            utility_inflation=self.num(escalation, "utilities", "dcf.escalation", _rate),
            discount_rate=discount_rate,
            tax=DcfTaxAssumptions(
                fed_rate=self.num(tax, "fed_rate", "dcf.tax", _fraction),
                state_rate=self.num(tax, "state_rate", "dcf.tax", _fraction),
                fed_bonus=self.num(tax, "fed_bonus", "dcf.tax", _fraction),
                fed_improvement_life=self.num(tax, "fed_improvement_life", "dcf.tax", v.positive),
                fed_equipment_life=self.num(tax, "fed_equipment_life", "dcf.tax", v.positive),
                state_improvement_life=self.num(
                    tax, "state_improvement_life", "dcf.tax", v.positive
                ),
                state_equipment_life=self.num(tax, "state_equipment_life", "dcf.tax", v.positive),
            ),
            terminal=terminal_mode,
            terminal_growth=terminal_growth,
        )

    # -- scalar readers ------------------------------------------------------------

    def num(self, section: Mapping[str, object], key: str, where: str, check: Check) -> float:
        """Read a number or a ``{low, base, high}`` range; return the checked base value."""
        path = f"{where}.{key}"
        value = section[key]
        if isinstance(value, Mapping):
            rng = _section(value, path)
            _exact_keys(path, rng, {"low", "base", "high"})
            low = check(f"{path}.low", _num(rng, "low", path))
            base = check(f"{path}.base", _num(rng, "base", path))
            high = check(f"{path}.high", _num(rng, "high", path))
            if not low <= base <= high:
                raise AssumptionsError(
                    f"{path} must satisfy low <= base <= high; got {low}, {base}, {high}"
                )
            self.ranges[path] = ValueRange(low=low, base=base, high=high)
            return base
        return check(path, _num(section, key, where))

    def integer(self, section: Mapping[str, object], key: str, where: str) -> int:
        """Like :meth:`num` but every value must be a positive whole number."""
        base = self.num(section, key, where, _positive_whole)
        return int(base)


# -- value checks --------------------------------------------------------------------


def _wage_load(name: str, value: float) -> float:
    out = v.positive(name, value)
    if out < 1.0:
        raise AssumptionsError(
            f"{name} is a multiplier on base wages (1.30 means +30%); "
            f"got {value!r}, which would pay less than the base wage"
        )
    return out


def _at_least_one(name: str, value: float) -> float:
    out = v.finite(name, value)
    if out < 1.0:
        raise AssumptionsError(f"{name} is a multiplier and must be >= 1; got {value!r}")
    return out


def _fraction(name: str, value: float) -> float:
    out = v.non_negative(name, value)
    if out > 1.0:
        raise AssumptionsError(f"{name} is a fraction and must be <= 1; got {value!r}")
    return out


def _share(name: str, value: float) -> float:
    """A Tesla share of EV sales: greater than 0 and at most 1."""
    out = v.positive(name, value)
    if out > 1.0:
        raise AssumptionsError(f"{name} is a share of EV sales and must be <= 1; got {value!r}")
    return out


def _rate(name: str, value: float) -> float:
    """A yearly growth or escalation rate: finite and above -100%."""
    return v.shock(name, value)


def _positive_whole(name: str, value: float) -> float:
    out = v.positive(name, value)
    if out != math.floor(out):
        raise AssumptionsError(f"{name} must be a whole number; got {value!r}")
    return out


# -- structured sections -------------------------------------------------------------


def _vehicle_mix(value: object) -> dict[str, float]:
    s = _section(value, "vehicle_mix")
    if not s:
        raise AssumptionsError("vehicle_mix must not be empty")
    mix = {name: v.non_negative(f"vehicle_mix.{name}", _num(s, name, "vehicle_mix")) for name in s}
    _sums_to_one("vehicle_mix", list(mix.values()))
    return mix


def _wage_mix(value: object) -> tuple[WageMixEntry, ...]:
    if not isinstance(value, list) or not value:
        raise AssumptionsError("labor.wage_mix must be a non-empty list")
    entries: list[WageMixEntry] = []
    for i, item in enumerate(value):
        where = f"labor.wage_mix[{i}]"
        s = _section(item, where)
        _exact_keys(where, s, {"socs", "title", "share"})
        socs = s["socs"]
        if not isinstance(socs, list) or not socs:
            raise AssumptionsError(f"{where}.socs must be a non-empty list of SOC codes")
        for soc in socs:
            if not isinstance(soc, str) or not _SOC_PATTERN.match(soc):
                raise AssumptionsError(f"{where}.socs has {soc!r}; expected a code like '41-2031'")
        entries.append(
            WageMixEntry(
                socs=tuple(cast(list[str], socs)),
                title=_text(s, "title", where),
                share=v.non_negative(f"{where}.share", _num(s, "share", where)),
            )
        )
    _sums_to_one("labor.wage_mix shares", [e.share for e in entries])
    return tuple(entries)


def _seasonality(value: object) -> SeasonalityAssumptions:
    s = _section(value, "seasonality")
    _exact_keys("seasonality", s, {"quarter_shares", "month_in_quarter"})
    quarters = _vector(s["quarter_shares"], "seasonality.quarter_shares", length=4)
    _sums_to_one("seasonality.quarter_shares", list(quarters))
    low, base, high = _vector_range(s, "month_in_quarter", "seasonality", length=3)
    for label, split in (("low", low), ("base", base), ("high", high)):
        _sums_to_one(f"seasonality.month_in_quarter.{label}", list(split))
    return SeasonalityAssumptions(
        quarter_shares=(quarters[0], quarters[1], quarters[2], quarters[3]),
        month_in_quarter=(base[0], base[1], base[2]),
        month_in_quarter_low=(low[0], low[1], low[2]),
        month_in_quarter_high=(high[0], high[1], high[2]),
    )


def _vector_range(
    section: Mapping[str, object], key: str, where: str, *, length: int | None
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    path = f"{where}.{key}"
    rng = _section(section[key], path)
    _exact_keys(path, rng, {"low", "base", "high"})
    low = _vector(rng["low"], f"{path}.low", length=length)
    base = _vector(rng["base"], f"{path}.base", length=length)
    high = _vector(rng["high"], f"{path}.high", length=length)
    if not len(low) == len(base) == len(high):
        raise AssumptionsError(f"{path} low, base, and high must have the same length")
    return low, base, high


def _vector(value: object, where: str, *, length: int | None) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise AssumptionsError(f"{where} must be a non-empty list of numbers")
    if length is not None and len(value) != length:
        raise AssumptionsError(f"{where} must have {length} values; got {len(value)}")
    out: list[float] = []
    for i, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise AssumptionsError(f"{where}[{i}] must be a number; got {type(item).__name__}")
        out.append(v.non_negative(f"{where}[{i}]", float(item)))
    return tuple(out)


def _sums_to_one(where: str, values: list[float]) -> None:
    total = math.fsum(values)
    if abs(total - 1.0) > _SUM_TOLERANCE:
        raise AssumptionsError(f"{where} must sum to 1; got {total!r}")


def _factor(factors: Mapping[str, object], name: str) -> DemandFactor:
    where = f"demand.factors.{name}"
    section = _section(factors[name], where)
    _exact_keys(where, section, {"reference", "elasticity"})
    return DemandFactor(
        reference=v.positive(f"{where}.reference", _num(section, "reference", where)),
        elasticity=v.finite(f"{where}.elasticity", _num(section, "elasticity", where)),
    )


# -- primitive readers ---------------------------------------------------------------


def _section(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AssumptionsError(f"{where} must be a mapping; got {type(value).__name__}")
    for key in value:
        if not isinstance(key, str):
            raise AssumptionsError(f"{where} has a non-text key {key!r}")
    return value


def _exact_keys(where: str, section: Mapping[str, object], expected: set[str]) -> None:
    keys = set(section)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if missing:
        raise AssumptionsError(f"{where} is missing {missing}")
    if unknown:
        raise AssumptionsError(f"{where} has unknown keys {unknown}")


def _num(section: Mapping[str, object], key: str, where: str) -> float:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AssumptionsError(f"{where}.{key} must be a number; got {type(value).__name__}")
    return float(value)


def _bool(section: Mapping[str, object], key: str, where: str) -> bool:
    value = section[key]
    if not isinstance(value, bool):
        raise AssumptionsError(f"{where}.{key} must be true or false; got {type(value).__name__}")
    return value


def _choice(section: Mapping[str, object], key: str, where: str, allowed: tuple[str, ...]) -> str:
    value = _text(section, key, where)
    if value not in allowed:
        raise AssumptionsError(f"{where}.{key} must be one of {list(allowed)}; got {value!r}")
    return value


def _text(section: Mapping[str, object], key: str, where: str) -> str:
    value = section[key]
    # PyYAML turns an unquoted ISO date into ``datetime.date``. Accept it as text.
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise AssumptionsError(f"{where}.{key} must be text; got {type(value).__name__}")
    if not value.strip():
        raise AssumptionsError(f"{where}.{key} must not be empty")
    return value
