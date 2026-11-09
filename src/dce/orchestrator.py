"""ZIP-in, estimate-out orchestration.

Contract
--------
``estimate(zip_code, scenario=None, overrides=None) -> EstimateResult``

One call runs the whole pipeline. The only required argument is a 5-digit
US ZIP. The steps are:

1. Resolve the ZIP to county, CBSA, and state.
2. Build the gravity catchment (beta 2). Nearest-center is the low case.
3. Feed the gravity deliveries per year into the cost model.
4. Run both DCF benefit views at that steady volume. The default discount
   rate is the Tesla WACC on the assumptions table, 13.6%.

Inputs come from the committed seed and the San Mateo demo cache. There is
no network call and no prompt. ``overrides`` may carry ``rent_psf_month``
for a sensitivity check. A missing override still resolves rent from the
demo file.

Do not import ``dce.extract.pdf_llm``. Do not call an LLM. Same files + ZIP
+ scenario must yield identical floats.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import yaml

from dce.config import assumptions_path
from dce.data.catchment_demand import build_catchment_demand, delivery_center_sites
from dce.data.operating_inputs import OperatingInputError, load_san_mateo_operating_inputs
from dce.geo.catchment import CatchmentCase, CatchmentFeatures, catchment_features
from dce.geo.resolve import resolve_zip
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import annualized_components, annualized_total, build_cost_inputs
from dce.model.costs import cost_per_delivery as cost_per_delivery_of
from dce.model.dcf import run_dcf_views
from dce.model.demand import apply_delivery_shock
from dce.model.drivers import top_drivers
from dce.model.types import (
    CatchmentCaseSummary,
    CatchmentSummary,
    CatchmentZipVolume,
    CenterVolumeTaken,
    EstimateResult,
    Scenario,
)

# Optional advanced overrides. ZIP alone must still run.
Overrides = Mapping[str, object]
_RENT_OVERRIDE = "rent_psf_month"


class EstimateDataError(ValueError):
    """A local input the estimate needs is missing or not usable."""


def estimate(
    zip_code: str,
    scenario: Scenario | None = None,
    overrides: Overrides | None = None,
) -> EstimateResult:
    """Run catchment, cost, and both DCF views for ``zip_code``."""
    geo = resolve_zip(zip_code)
    assumptions = parse_assumptions(_load_assumptions())
    chosen = scenario if scenario is not None else _baseline_scenario(assumptions)
    rent = _rent_psf_month(geo.state, overrides)
    rates = load_san_mateo_operating_inputs()
    features = catchment_features(
        geo,
        delivery_center_sites(),
        build_catchment_demand(geo),
    )
    steady = features.gravity.total_deliveries_per_year
    shocked = apply_delivery_shock(steady, chosen)
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=rent,
        wage_annual=assumptions.labor.fallback_wage_hourly * assumptions.labor.paid_hours_per_fte,
        energy_rate_kwh=rates.energy_rate_kwh,
        demand_rate_kw=rates.demand_rate_kw,
        annual_deliveries=shocked,
    )
    components = annualized_components(costs, chosen)
    return EstimateResult(
        geo=geo,
        scenario=chosen,
        cost_per_delivery=cost_per_delivery_of(components, shocked),
        annualized_total_cost=annualized_total(components),
        estimated_annual_deliveries=shocked,
        components=components,
        drivers=top_drivers(components),
        map_path=None,
        catchment=_summarize(features),
        dcf=run_dcf_views(
            costs,
            assumptions,
            steady_deliveries=steady,
            scenario=chosen,
        ),
    )


def _load_assumptions() -> dict[str, object]:
    path = assumptions_path()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise EstimateDataError(f"Could not read assumptions: {path}.") from exc
    except yaml.YAMLError as exc:
        raise EstimateDataError(f"Assumptions file is not valid YAML: {path}.") from exc
    if not isinstance(loaded, dict):
        raise EstimateDataError("Assumptions file must be a mapping.")
    return {str(key): value for key, value in loaded.items()}


def _baseline_scenario(assumptions: ModelAssumptions) -> Scenario:
    return Scenario(
        vehicle_mix=dict(assumptions.vehicle_mix),
        wage_shock=0.0,
        rent_shock=0.0,
        delivery_shock=0.0,
    )


def _rent_psf_month(state: str, overrides: Overrides | None) -> float:
    """Return monthly NNN rent. An override replaces the demo figure."""
    if overrides:
        unknown = sorted(set(overrides) - {_RENT_OVERRIDE})
        if unknown:
            raise EstimateDataError(
                "Unknown override "
                + ", ".join(unknown)
                + ". The optional override is rent_psf_month."
            )
        if _RENT_OVERRIDE in overrides:
            return _finite_rent(overrides[_RENT_OVERRIDE])
    if state != "CA":
        raise OperatingInputError(
            "Resolved rent is bundled for the San Mateo demo. "
            "A non-California ZIP needs the rent fallback, which is not wired yet, "
            "or an explicit rent_psf_month override."
        )
    return load_san_mateo_operating_inputs().rent_psf_month


def _finite_rent(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EstimateDataError(f"rent_psf_month must be a finite number, got {value!r}.")
    if value < 0:
        raise EstimateDataError(f"rent_psf_month must be >= 0, got {value}.")
    return float(value)


def _summarize(features: CatchmentFeatures) -> CatchmentSummary:
    return CatchmentSummary(
        zip_code=features.zip_code,
        beta=features.beta,
        gravity=_case(features.gravity),
        nearest=_case(features.nearest),
    )


def _case(case: CatchmentCase) -> CatchmentCaseSummary:
    return CatchmentCaseSummary(
        method=case.method,
        beta=case.beta,
        zips=tuple(
            CatchmentZipVolume(row.zip_code, row.deliveries_per_year, row.share)
            for row in case.zips
        ),
        deliveries_per_year=case.total_deliveries_per_year,
        taken_from=tuple(
            CenterVolumeTaken(row.center_id, row.name, row.deliveries_per_year)
            for row in case.taken_from
        ),
    )


__all__ = ["EstimateDataError", "estimate"]
