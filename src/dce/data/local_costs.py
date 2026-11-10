"""Local electricity, property tax, and fit-out index for one ZIP.

The fit-out index is the DoD construction area cost factor
(:mod:`dce.data.construction_cost`). The BEA goods price parity is only its
fallback.

Rent and wages stay on ``load_zip_local``. This module does not open
SQLite and does not use the network. ``estimate`` reads the bundled CSVs.
"""

from __future__ import annotations

from dataclasses import dataclass

from dce.data.construction_cost import ConstructionCostResolution, resolve_construction_cost
from dce.data.electricity import ElectricityResolution, resolve_electricity
from dce.data.property_tax import PropertyTaxResolution, resolve_property_tax
from dce.model.assumptions import ModelAssumptions
from dce.model.costs import nnn_opex_load
from dce.model.types import GeoContext

# Kidder Mathews Peninsula Industrial Q3 2026, San Mateo asking NNN.
# The assumptions file stores the South San Francisco figure, $1.74.
KIDDER_SAN_MATEO_ASKING_PSF_MONTH = 2.14


@dataclass(frozen=True)
class LocalPrices:
    """Place-specific prices that sit on top of the ZIP's own rent and wage."""

    electricity: ElectricityResolution
    property_tax: PropertyTaxResolution
    construction: ConstructionCostResolution
    opex_load: float
    fitout_index: float
    status_quo_rent_psf_month: float


def resolve_local_prices(
    geo: GeoContext, assumptions: ModelAssumptions, rent_psf_month: float
) -> LocalPrices:
    """Return electricity, the NNN load, the fit-out index, and status-quo rent."""
    electricity = resolve_electricity(geo)
    tax = resolve_property_tax(geo)
    construction = resolve_construction_cost(geo)
    if assumptions.property_tax.included_in_nnn:
        load = nnn_opex_load(
            assumptions.facility.opex_load,
            reference_rate=assumptions.property_tax.effective_rate,
            local_rate=tax.effective_rate,
            assessed_value_psf=assumptions.property_tax.assessed_value_psf,
            rent_psf_year=rent_psf_month * 12.0,
        )
    else:
        load = assumptions.facility.opex_load
    return LocalPrices(
        electricity=electricity,
        property_tax=tax,
        construction=construction,
        opex_load=load,
        fitout_index=construction.fitout_index,
        status_quo_rent_psf_month=_status_quo(assumptions, rent_psf_month),
    )


def _status_quo(assumptions: ModelAssumptions, rent_psf_month: float) -> float:
    asking = KIDDER_SAN_MATEO_ASKING_PSF_MONTH
    published = assumptions.dcf.status_quo_rent_psf_month
    if rent_psf_month == asking or asking == 0.0:
        return published
    return rent_psf_month * (published / asking)
