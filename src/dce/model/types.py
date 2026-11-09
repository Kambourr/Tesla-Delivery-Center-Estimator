"""Frozen dataclasses shared by the model and the orchestrator.

These types are the contract in ``docs/MODULE_CONTRACTS.md``. They carry
data only: no constructors beyond the dataclass defaults and no
calculation methods. Validation happens in the functions that consume them
(``dce.model.demand``, ``dce.model.costs``, ``dce.model.drivers``).

Units: money is USD, periods are per year unless the name says ``month``.
``CostInputs.opex_load`` is a fraction (0.15 means +15%).
``CostInputs.wage_load`` is a multiplier (1.30 means +30%).
``CostInputs.demand_rate_kw`` is USD per kW per month.

``CostInputs.rent_psf_month`` is the rent the model should use after
:func:`dce.data.rent_resolver.resolve_rent` (or after an optional advanced
override). The model does not look up rent itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for the annotation on EstimateResult.dcf; dce.model.dcf imports
    # this module, so a runtime import would be circular.
    from dce.model.dcf import DcfViews

# Assumption tables mix numbers, strings, and nested presets. Callers pass a
# mapping; the model reads the keys it knows. Not a pydantic model: the
# shapes are small and already frozen dataclasses.
Assumptions = Mapping[str, object]


@dataclass(frozen=True)
class Scenario:
    """One what-if case. Shocks are fractions (``0.2`` means +20%)."""

    vehicle_mix: dict[str, float]
    wage_shock: float
    rent_shock: float = 0.0
    delivery_shock: float = 0.0


@dataclass(frozen=True)
class GeoContext:
    """Geographies joined from a ZIP. All codes are text."""

    zip_code: str
    zcta: str
    county_fips: str
    cbsa: str
    state: str


@dataclass(frozen=True)
class DemandInputs:
    """Public demand-proxy inputs for one catchment."""

    population: float
    median_hh_income: float
    ev_stock: float
    total_ldv: float
    mean_commute: float
    catchment_population: float


@dataclass(frozen=True)
class CostInputs:
    """Physical inputs for one year of delivery-center cost. No I/O."""

    sqft: float
    rent_psf_month: float
    opex_load: float
    wage_annual: float
    wage_load: float
    headcount: float
    kwh_per_year: float
    energy_rate_kwh: float
    demand_kw: float
    demand_rate_kw: float
    property_tax_annual: float
    capex_total: float
    capex_years: float
    other_opex_annual: float


@dataclass(frozen=True)
class Driver:
    """One cost component's dollars and share of annualized total cost."""

    name: str
    usd: float
    share: float


@dataclass(frozen=True)
class EstimateResult:
    """Full result for one ZIP and one scenario.

    ``components`` is the static annualized view (capex straight-line).
    ``dcf`` is the optional cash-flow view: the standalone lens (headline)
    and the incremental lens (check), with capex as year-0 cash (ADR-0005).
    """

    geo: GeoContext
    scenario: Scenario
    cost_per_delivery: float
    annualized_total_cost: float
    estimated_annual_deliveries: float
    components: dict[str, float]
    drivers: list[Driver]
    map_path: str | None
    dcf: DcfViews | None = None
