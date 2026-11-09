"""San Mateo 94402 inputs for the scenario tests (dcf_design.md §2, base column).

Rent, wage, and PG&E rates are resolved inputs in the app; the tests supply
the research values. File reads happen here, never in ``dce.scenarios``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.types import CostInputs, GeoContext

REPO = Path(__file__).resolve().parents[3]
ASSUMPTIONS_YAML = REPO / "data" / "defaults" / "assumptions.yaml"

# The goldens in this folder were computed on this version of the defaults.
ASSUMPTIONS_VERSION = "2026.11.1"

STEADY = 4_400.0  # nearest-center capture 4,370, rounded (research §4.4)
RENT = 2.14  # Kidder Mathews Peninsula Industrial Q3 2026, San Mateo
WAGE_HOURLY = 25.91  # blended Tesla Bay Area postings, Nov 2026
ENERGY = 0.2875  # PG&E B-10, effective 2026-03-01
DEMAND_RATE = 20.50  # PG&E B-10 demand charge, $/kW-month

GEO = GeoContext(zip_code="94402", zcta="94402", county_fips="06081", cbsa="41884", state="CA")


def load_assumptions() -> ModelAssumptions:
    raw = yaml.safe_load(ASSUMPTIONS_YAML.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    parsed = parse_assumptions(raw)
    assert parsed.assumptions_version == ASSUMPTIONS_VERSION, (
        "assumptions.yaml values changed; recompute the scenario goldens"
    )
    return parsed


def san_mateo_costs(assumptions: ModelAssumptions, deliveries: float = STEADY) -> CostInputs:
    return build_cost_inputs(
        assumptions,
        rent_psf_month=RENT,
        wage_annual=WAGE_HOURLY * assumptions.labor.paid_hours_per_fte,
        energy_rate_kwh=ENERGY,
        demand_rate_kw=DEMAND_RATE,
        annual_deliveries=deliveries,
    )
