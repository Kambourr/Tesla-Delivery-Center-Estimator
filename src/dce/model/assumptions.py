"""Typed view of the modeling assumptions table.

The default table ships as ``data/defaults/assumptions.yaml``. Reading that
file is I/O, so it happens outside the model (the orchestrator, or a test).
The caller passes the parsed mapping in; :func:`parse_assumptions` checks
its shape and returns frozen dataclasses. Pure: no file access here.

Parsing is strict. An unknown key, a missing key, a wrong type, or an
unsupported ``schema_version`` raises :class:`AssumptionsError`, so a typo
in the YAML fails loudly instead of silently using a default.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from dce.model import _validate as v
from dce.model.errors import AssumptionsError, InvalidInputError
from dce.model.types import Assumptions

SUPPORTED_SCHEMA_VERSIONS: frozenset[int] = frozenset({1})


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
class LaborAssumptions:
    wage_load: float
    staffing: StaffingAssumptions


@dataclass(frozen=True)
class UtilityAssumptions:
    kwh_per_sqft_year: float
    peak_kw_per_sqft: float


@dataclass(frozen=True)
class PropertyTaxAssumptions:
    assessed_value_psf: float
    effective_rate: float


@dataclass(frozen=True)
class CapexAssumptions:
    fitout_psf: float
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


@dataclass(frozen=True)
class ModelAssumptions:
    schema_version: int
    assumptions_version: str
    as_of: str
    facility: FacilityAssumptions
    labor: LaborAssumptions
    utilities: UtilityAssumptions
    property_tax: PropertyTaxAssumptions
    capex: CapexAssumptions
    other_opex: OtherOpexAssumptions
    demand: DemandAssumptions


def parse_assumptions(raw: Assumptions | ModelAssumptions) -> ModelAssumptions:
    """Validate an assumptions mapping and return the typed view.

    A :class:`ModelAssumptions` passes through unchanged, so model functions
    accept either the raw mapping or an already parsed table.
    """
    if isinstance(raw, ModelAssumptions):
        return raw
    try:
        return _parse(raw)
    except AssumptionsError:
        raise
    except InvalidInputError as exc:
        raise AssumptionsError(str(exc)) from exc


def _parse(raw: Assumptions) -> ModelAssumptions:
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
            "utilities",
            "property_tax",
            "capex",
            "other_opex",
            "demand",
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

    facility = _section(root["facility"], "facility")
    _exact_keys("facility", facility, {"sqft", "opex_load", "catchment_miles"})

    labor = _section(root["labor"], "labor")
    _exact_keys("labor", labor, {"wage_load", "staffing"})
    staffing = _section(labor["staffing"], "labor.staffing")
    _exact_keys("labor.staffing", staffing, {"min_headcount", "deliveries_per_fte"})
    wage_load = v.positive("labor.wage_load", _num(labor, "wage_load", "labor"))
    if wage_load < 1.0:
        raise AssumptionsError(
            "labor.wage_load is a multiplier on base wages (1.30 means +30%); "
            f"got {wage_load!r}, which would pay less than the base wage"
        )

    utilities = _section(root["utilities"], "utilities")
    _exact_keys("utilities", utilities, {"kwh_per_sqft_year", "peak_kw_per_sqft"})

    tax = _section(root["property_tax"], "property_tax")
    _exact_keys("property_tax", tax, {"assessed_value_psf", "effective_rate"})

    capex = _section(root["capex"], "capex")
    _exact_keys("capex", capex, {"fitout_psf", "life_years"})

    other = _section(root["other_opex"], "other_opex")
    _exact_keys("other_opex", other, {"pct_of_lease_and_labor"})

    demand = _section(root["demand"], "demand")
    _exact_keys(
        "demand",
        demand,
        {"base_annual_deliveries", "factors", "score_min", "score_max"},
    )
    factors = _section(demand["factors"], "demand.factors")
    _exact_keys(
        "demand.factors",
        factors,
        {"catchment_population", "median_hh_income", "ev_share", "mean_commute"},
    )
    score_min = v.non_negative("demand.score_min", _num(demand, "score_min", "demand"))
    score_max = v.positive("demand.score_max", _num(demand, "score_max", "demand"))
    if score_min > score_max:
        raise AssumptionsError(
            f"demand.score_min ({score_min}) must not exceed demand.score_max ({score_max})"
        )

    return ModelAssumptions(
        schema_version=schema_version,
        assumptions_version=_text(root, "assumptions_version", "assumptions"),
        as_of=_text(root, "as_of", "assumptions"),
        facility=FacilityAssumptions(
            sqft=v.positive("facility.sqft", _num(facility, "sqft", "facility")),
            opex_load=v.non_negative("facility.opex_load", _num(facility, "opex_load", "facility")),
            catchment_miles=v.positive(
                "facility.catchment_miles", _num(facility, "catchment_miles", "facility")
            ),
        ),
        labor=LaborAssumptions(
            wage_load=wage_load,
            staffing=StaffingAssumptions(
                min_headcount=v.non_negative(
                    "labor.staffing.min_headcount",
                    _num(staffing, "min_headcount", "labor.staffing"),
                ),
                deliveries_per_fte=v.positive(
                    "labor.staffing.deliveries_per_fte",
                    _num(staffing, "deliveries_per_fte", "labor.staffing"),
                ),
            ),
        ),
        utilities=UtilityAssumptions(
            kwh_per_sqft_year=v.non_negative(
                "utilities.kwh_per_sqft_year",
                _num(utilities, "kwh_per_sqft_year", "utilities"),
            ),
            peak_kw_per_sqft=v.non_negative(
                "utilities.peak_kw_per_sqft",
                _num(utilities, "peak_kw_per_sqft", "utilities"),
            ),
        ),
        property_tax=PropertyTaxAssumptions(
            assessed_value_psf=v.non_negative(
                "property_tax.assessed_value_psf",
                _num(tax, "assessed_value_psf", "property_tax"),
            ),
            effective_rate=v.non_negative(
                "property_tax.effective_rate", _num(tax, "effective_rate", "property_tax")
            ),
        ),
        capex=CapexAssumptions(
            fitout_psf=v.non_negative("capex.fitout_psf", _num(capex, "fitout_psf", "capex")),
            life_years=v.positive("capex.life_years", _num(capex, "life_years", "capex")),
        ),
        other_opex=OtherOpexAssumptions(
            pct_of_lease_and_labor=v.non_negative(
                "other_opex.pct_of_lease_and_labor",
                _num(other, "pct_of_lease_and_labor", "other_opex"),
            ),
        ),
        demand=DemandAssumptions(
            base_annual_deliveries=v.positive(
                "demand.base_annual_deliveries",
                _num(demand, "base_annual_deliveries", "demand"),
            ),
            catchment_population=_factor(factors, "catchment_population"),
            median_hh_income=_factor(factors, "median_hh_income"),
            ev_share=_factor(factors, "ev_share"),
            mean_commute=_factor(factors, "mean_commute"),
            score_min=score_min,
            score_max=score_max,
        ),
    )


def _factor(factors: Mapping[str, object], name: str) -> DemandFactor:
    where = f"demand.factors.{name}"
    section = _section(factors[name], where)
    _exact_keys(where, section, {"reference", "elasticity"})
    return DemandFactor(
        reference=v.positive(f"{where}.reference", _num(section, "reference", where)),
        elasticity=v.finite(f"{where}.elasticity", _num(section, "elasticity", where)),
    )


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
