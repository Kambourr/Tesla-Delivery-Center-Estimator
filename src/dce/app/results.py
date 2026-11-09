"""Build the JSON document the map dashboard renders.

Headline cost, deliveries, catchment, and both DCF views come from
:func:`dce.orchestrator.estimate` with its own defaults, including the base
handover factor. This module does not rebuild ZIP demand or pick a
handover factor of its own. Low / base / high cards and the NPV tornado
come from ``dce.scenarios``, using that estimate's volume and the parsed
assumption file's base prices. Do not import ``dce.extract.pdf_llm``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from dce.app.mapdata import load_centers, lookup_centroid
from dce.config import assumptions_path
from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.dcf import DcfResult
from dce.model.types import (
    CatchmentCaseSummary,
    CatchmentSummary,
    CostInputs,
    EstimateResult,
    GeoContext,
    Scenario,
)
from dce.orchestrator import EstimateDataError, estimate
from dce.scenarios import (
    TornadoInputs,
    dcf_tornado,
    outcome_scenarios,
    run_scenario_grid,
    tornado_rows,
)
from dce.scenarios.types import ScenarioResult

UI_RESULT_SCHEMA = "dce.ui_result.v1"
UI_COMPARE_SCHEMA = "dce.ui_compare.v1"
UI_MAP_SCHEMA = "dce.ui_map.v1"
# Wall-clock time is not part of the document. Two runs of the same inputs
# write this same timestamp so the JSON is byte-identical.
COMPUTED_AT = "2026-11-09T00:00:00+00:00"

_DRIVER_LABELS = {
    "labor": "Labor",
    "lease": "Lease",
    "capex": "Capex",
    "utilities": "Utilities",
    "property_tax": "Property tax",
    "other_opex": "Other operating",
}
_NEARBY_LIMIT = 5
_EARTH_MILES = 3958.7613

# Compare rows. ``better`` is ``lower`` or ``higher``. A missing IRR or
# payback (the model uses None for "never") loses to a real number.
COMPARE_METRICS: tuple[tuple[str, str, str, str], ...] = (
    ("cost_per_delivery", "Cost / delivery", "lower", "usd"),
    ("estimated_annual_deliveries", "Annual deliveries", "higher", "count"),
    ("standalone_npv", "Standalone NPV", "higher", "usd"),
    ("standalone_irr", "Standalone IRR", "higher", "ratio"),
    ("standalone_simple_payback_years", "Simple payback", "lower", "years"),
    ("standalone_discounted_payback_years", "Discounted payback", "lower", "years"),
    ("incremental_npv", "Incremental NPV", "higher", "usd"),
    ("incremental_irr", "Incremental IRR", "higher", "ratio"),
    ("incremental_simple_payback_years", "Incremental simple payback", "lower", "years"),
    ("incremental_discounted_payback_years", "Incremental discounted payback", "lower", "years"),
)


@dataclass(frozen=True)
class _Prepared:
    geo: GeoContext
    assumptions: ModelAssumptions
    scenario: Scenario
    costs: CostInputs
    steady: float
    catchment: CatchmentSummary
    result: EstimateResult
    lat: float
    lon: float


def build_ui_result(
    zip_code: str,
    *,
    source: str = "computed",
    computed_at: str = COMPUTED_AT,
    data_dir: Path | None = None,
) -> dict[str, object]:
    """Return the dashboard document for one ZIP. No network.

    ``source`` is ``computed`` for a live call and ``precomputed`` for a
    stored row. ``computed_at`` defaults to the input vintage, not the
    clock, so a second run of the same inputs is the same document.
    ``data_dir`` is forwarded to ``estimate`` when a batch uses its own
    database.
    """
    prepared = _prepare(zip_code, data_dir=data_dir)
    scenarios = run_scenario_grid(
        prepared.geo,
        prepared.steady,
        prepared.costs,
        outcome_scenarios(prepared.assumptions),
        prepared.assumptions,
        catchment=prepared.catchment,
        provenance=prepared.result.provenance,
        nearby_centers=prepared.result.nearby_centers,
    )
    bars = dcf_tornado(
        TornadoInputs(
            costs=prepared.costs,
            assumptions=prepared.assumptions,
            steady_deliveries=prepared.steady,
            scenario=prepared.scenario,
            benefit_mode="standalone",
        )
    )
    result = prepared.result
    dcf = result.dcf
    if dcf is None or result.catchment is None:
        raise EstimateDataError(f"ZIP {zip_code} did not produce a catchment and a DCF.")
    return {
        "schema": UI_RESULT_SCHEMA,
        "zip_code": result.geo.zip_code,
        "source": source,
        "computed_at": computed_at,
        "geo": {
            "zip_code": result.geo.zip_code,
            "zcta": result.geo.zcta,
            "county_fips": result.geo.county_fips,
            "cbsa": result.geo.cbsa,
            "state": result.geo.state,
        },
        "centroid": {"lat": prepared.lat, "lon": prepared.lon},
        "cost_per_delivery": result.cost_per_delivery,
        "annualized_total_cost": result.annualized_total_cost,
        "estimated_annual_deliveries": result.estimated_annual_deliveries,
        "components": dict(result.components),
        "drivers": [
            {
                "name": driver.name,
                "label": _DRIVER_LABELS.get(driver.name, driver.name.replace("_", " ").title()),
                "usd": driver.usd,
                "share": driver.share,
            }
            for driver in result.drivers
        ],
        "catchment": {
            "beta": result.catchment.beta,
            "gravity": _case(result.catchment.gravity),
            "nearest": _case(result.catchment.nearest),
        },
        "dcf": {
            "standalone": _lens(dcf.standalone),
            "incremental": _lens(dcf.incremental),
        },
        "scenarios": {row.scenario_id: _scenario_card(row) for row in scenarios},
        "tornado": tornado_rows(bars),
        "nearby_centers": _nearby(prepared),
        "provenance": [asdict(row) for row in result.provenance],
    }


def compare_metrics(left: dict[str, object], right: dict[str, object]) -> list[dict[str, object]]:
    """Return one row per key metric, with ``winner`` of ``a``, ``b``, or ``tie``."""
    rows: list[dict[str, object]] = []
    for metric_id, label, better, fmt in COMPARE_METRICS:
        a_value = _metric_value(left, metric_id)
        b_value = _metric_value(right, metric_id)
        rows.append(
            {
                "id": metric_id,
                "label": label,
                "better": better,
                "format": fmt,
                "a": a_value,
                "b": b_value,
                "winner": _winner(better, a_value, b_value),
            }
        )
    return rows


def ui_result_problems(payload: object) -> list[str]:
    """Return contract problems. An empty list means the document is usable."""
    if not isinstance(payload, dict):
        return ["result is not an object"]
    problems: list[str] = []
    required = (
        "schema",
        "zip_code",
        "geo",
        "centroid",
        "cost_per_delivery",
        "annualized_total_cost",
        "estimated_annual_deliveries",
        "drivers",
        "components",
        "catchment",
        "dcf",
        "scenarios",
        "tornado",
        "nearby_centers",
        "computed_at",
    )
    for key in required:
        if key not in payload:
            problems.append(f"missing {key}")
    if payload.get("schema") != UI_RESULT_SCHEMA:
        problems.append("schema")
    drivers = payload.get("drivers")
    if not isinstance(drivers, list) or len(drivers) < 1:
        problems.append("drivers")
    elif isinstance(drivers[0], dict):
        for field in ("name", "label", "usd", "share"):
            if field not in drivers[0]:
                problems.append(f"driver.{field}")
    dcf = payload.get("dcf")
    if isinstance(dcf, dict):
        for lens in ("standalone", "incremental"):
            block = dcf.get(lens)
            if not isinstance(block, dict):
                problems.append(lens)
                continue
            for field in (
                "npv",
                "irr",
                "simple_payback_years",
                "discounted_payback_years",
                "years",
            ):
                if field not in block:
                    problems.append(f"{lens}.{field}")
            years = block.get("years")
            if not isinstance(years, list) or len(years) < 11:
                problems.append(f"{lens}.years length")
    else:
        problems.append("dcf")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, dict) or not {"low", "base", "high"} <= set(scenarios):
        problems.append("scenarios")
    tornado = payload.get("tornado")
    if not isinstance(tornado, list) or not tornado:
        problems.append("tornado")
    elif isinstance(tornado[0], dict):
        for field in ("driver", "label", "npv_low", "npv_base", "npv_high", "swing"):
            if field not in tornado[0]:
                problems.append(f"tornado.{field}")
    catchment = payload.get("catchment")
    if isinstance(catchment, dict):
        gravity = catchment.get("gravity")
        if not isinstance(gravity, dict) or not isinstance(gravity.get("zips"), list):
            problems.append("catchment.gravity.zips")
    else:
        problems.append("catchment")
    return problems


def _prepare(zip_code: str, *, data_dir: Path | None = None) -> _Prepared:
    """Take the headline from ``estimate`` and the prices the scenarios need.

    ``estimate`` applies the base handover factor and the ZIP's own rent
    and wage. The scenario grid uses those same prices, read back from
    the result's provenance, so the base card matches the headline.
    """
    result = estimate(zip_code, data_dir=data_dir)
    if result.dcf is None or result.catchment is None:
        raise EstimateDataError(f"ZIP {zip_code} did not produce a catchment and a DCF.")
    assumptions = parse_assumptions(_load_assumptions())
    steady = result.catchment.gravity.deliveries_per_year
    values = {row.name: row.value for row in result.provenance}
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=_required(result.geo.zip_code, "rent_psf_month", values),
        wage_annual=_required(result.geo.zip_code, "wage_annual", values),
        energy_rate_kwh=_required(result.geo.zip_code, "energy_rate_kwh", values),
        demand_rate_kw=_required(result.geo.zip_code, "demand_rate_kw", values),
        annual_deliveries=steady,
    )
    point = lookup_centroid(result.geo.zcta) or lookup_centroid(result.geo.zip_code)
    if point is None:
        raise EstimateDataError(f"ZIP {result.geo.zip_code} has no centroid.")
    return _Prepared(
        geo=result.geo,
        assumptions=assumptions,
        scenario=result.scenario,
        costs=costs,
        steady=steady,
        catchment=result.catchment,
        result=result,
        lat=point[0],
        lon=point[1],
    )


def _required(zip_code: str, name: str, values: dict[str, float | None]) -> float:
    value = values.get(name)
    if value is None:
        raise EstimateDataError(f"ZIP {zip_code} has no {name} on its provenance.")
    return value


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


def _case(case: CatchmentCaseSummary) -> dict[str, object]:
    return {
        "method": case.method,
        "beta": case.beta,
        "deliveries_per_year": case.deliveries_per_year,
        "zips": [
            {
                "zip_code": row.zip_code,
                "deliveries_per_year": row.deliveries_per_year,
                "share": row.share,
            }
            for row in case.zips
        ],
        "taken_from": [
            {
                "center_id": row.center_id,
                "name": row.name,
                "deliveries_per_year": row.deliveries_per_year,
            }
            for row in case.taken_from
        ],
    }


def _lens(lens: DcfResult) -> dict[str, object]:
    return {
        "benefit_mode": lens.benefit_mode,
        "discount_rate": lens.discount_rate,
        "npv": lens.npv,
        "irr": lens.irr,
        "simple_payback_years": lens.simple_payback_years,
        "discounted_payback_years": lens.discounted_payback_years,
        "total_capex": lens.total_capex,
        "terminal_value": lens.terminal_value,
        "years": [
            {
                "year": row.year,
                "deliveries": row.deliveries,
                "headcount": row.headcount,
                "benefit": row.benefit,
                "lease": row.lease,
                "labor": row.labor,
                "utilities": row.utilities,
                "property_tax": row.property_tax,
                "other_opex": row.other_opex,
                "opex": row.opex,
                "ebitda": row.ebitda,
                "capex": row.capex,
                "fed_depreciation": row.fed_depreciation,
                "state_depreciation": row.state_depreciation,
                "tax": row.tax,
                "fcf": row.fcf,
                "discounted_fcf": row.discounted_fcf,
                "cumulative_fcf": row.cumulative_fcf,
                "cumulative_discounted_fcf": row.cumulative_discounted_fcf,
            }
            for row in lens.years
        ],
    }


def _scenario_card(row: ScenarioResult) -> dict[str, object]:
    result = row.result
    if result.dcf is None:
        raise EstimateDataError(f"Scenario {row.scenario_id} has no DCF.")
    return {
        "scenario_id": row.scenario_id,
        "label": row.named.label,
        "cost_per_delivery": result.cost_per_delivery,
        "annual_deliveries": result.estimated_annual_deliveries,
        "annualized_total_cost": result.annualized_total_cost,
        "standalone": _decision(result.dcf.standalone),
        "incremental": _decision(result.dcf.incremental),
    }


def _decision(lens: DcfResult) -> dict[str, object]:
    return {
        "npv": lens.npv,
        "irr": lens.irr,
        "simple_payback_years": lens.simple_payback_years,
        "discounted_payback_years": lens.discounted_payback_years,
        "discount_rate": lens.discount_rate,
    }


def _nearby(prepared: _Prepared) -> list[dict[str, object]]:
    taken = {
        row.center_id: row.deliveries_per_year for row in prepared.catchment.gravity.taken_from
    }
    ranked: list[tuple[float, dict[str, object]]] = []
    for center in load_centers():
        lat = center.get("lat")
        lon = center.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        distance = _haversine_miles(prepared.lat, prepared.lon, float(lat), float(lon))
        center_id = str(center["center_id"])
        ranked.append(
            (
                distance,
                {
                    "center_id": center_id,
                    "name": center["name"],
                    "city": center["city"],
                    "state": center["state"],
                    "distance_miles": distance,
                    "lat": float(lat),
                    "lon": float(lon),
                    "deliveries_taken": taken.get(center_id),
                },
            )
        )
    ranked.sort(key=lambda item: (item[0], str(item[1]["center_id"])))
    return [item for _, item in ranked[:_NEARBY_LIMIT]]


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lon / 2) ** 2
    return 2 * _EARTH_MILES * math.asin(math.sqrt(a))


def _metric_value(result: dict[str, object], metric_id: str) -> object:
    if metric_id in {"cost_per_delivery", "estimated_annual_deliveries"}:
        return result.get(metric_id)
    lens_name, _, field = metric_id.partition("_")
    # incremental_simple_payback_years -> lens incremental, field simple_payback_years.
    # The first underscore splits the lens name only when the lens is a single word.
    if lens_name not in {"standalone", "incremental"}:
        return None
    # partition splits on the first underscore, so "standalone_npv" works and
    # "incremental_simple_payback_years" keeps the rest of the field name.
    dcf = result.get("dcf")
    if not isinstance(dcf, dict):
        return None
    lens = dcf.get(lens_name)
    if not isinstance(lens, dict):
        return None
    return lens.get(field)


def _winner(better: str, left: object, right: object) -> str:
    left_missing = _missing(left)
    right_missing = _missing(right)
    if left_missing and right_missing:
        return "tie"
    if left_missing:
        return "b"
    if right_missing:
        return "a"
    a_value = float(left)  # type: ignore[arg-type]
    b_value = float(right)  # type: ignore[arg-type]
    if math.isclose(a_value, b_value, rel_tol=1e-9, abs_tol=1e-6):
        return "tie"
    if better == "lower":
        return "a" if a_value < b_value else "b"
    return "a" if a_value > b_value else "b"


def _missing(value: object) -> bool:
    return value is None or isinstance(value, bool) or not isinstance(value, (int, float))
