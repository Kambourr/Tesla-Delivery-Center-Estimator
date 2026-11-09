"""Low / base / high ranges the scenario layer reads, plus the rent range.

Every range comes from :attr:`dce.model.assumptions.ModelAssumptions.ranges`
(``data/defaults/assumptions.yaml``, schema 2) except rent. Rent is not in
the assumptions file because it arrives as a resolved number (ADR-0003), so
the research rent spread is hard-coded here as ratios to the base rent.

Rent ratios
-----------
Kidder Mathews, *Peninsula Industrial Market Report, Q3 2026*, NNN asking
rent, https://kidder.com/market-reports/peninsula-industrial-market-report/
(cited in ``docs/research/dcf_design.md`` §2, accessed 2026-11-08):

======  =====================  ===============
case    submarket              USD / SF / month
======  =====================  ===============
low     South San Francisco    1.74
base    San Mateo              2.14
high    Menlo Park             2.95
======  =====================  ===============

The ratios ``1.74 / 2.14`` and ``2.95 / 2.14`` scale whatever rent the
resolver returns for the candidate ZIP, so a non-Peninsula ZIP gets the same
relative spread around its own rent. Public data only.

Pure. No I/O.
"""

from __future__ import annotations

from collections.abc import Mapping

from dce.model.assumptions import ValueRange
from dce.model.errors import InvalidInputError

RENT_LOW_PSF_MONTH = 1.74  # Kidder Mathews Q3 2026, South San Francisco
RENT_BASE_PSF_MONTH = 2.14  # Kidder Mathews Q3 2026, San Mateo
RENT_HIGH_PSF_MONTH = 2.95  # Kidder Mathews Q3 2026, Menlo Park
RENT_CITATION = (
    "Kidder Mathews, Peninsula Industrial Market Report Q3 2026, NNN asking rent "
    "(https://kidder.com/market-reports/peninsula-industrial-market-report/)"
)

#: Rent as a multiple of the resolved base rent, ordered by input value.
RENT_RATIO = ValueRange(
    low=RENT_LOW_PSF_MONTH / RENT_BASE_PSF_MONTH,
    base=1.0,
    high=RENT_HIGH_PSF_MONTH / RENT_BASE_PSF_MONTH,
)

#: Optional ``ranges`` key that replaces :data:`RENT_RATIO` (a multiplier on
#: the resolved rent). Proposed for the assumptions file; see the PR notes.
RENT_RATIO_KEY = "facility.rent_multiplier"

# Dotted paths in ModelAssumptions.ranges.
DELIVERIES = "demand.base_annual_deliveries"
WAGE = "labor.fallback_wage_hourly"
WAGE_LOAD = "labor.wage_load"
DELIVERIES_PER_FTE = "labor.staffing.deliveries_per_fte"
MIN_HEADCOUNT = "labor.staffing.min_headcount"
FEE = "dcf.standalone.fee_per_delivery"
FREIGHT = "dcf.standalone.inbound_freight"
DISCOUNT_RATE = "dcf.discount_rate"
HORIZON = "dcf.horizon_years"
GROWTH = "dcf.volume.growth"
FITOUT = "capex.fitout_psf"
EQUIPMENT = "capex.equipment_usd"
RENT_ESCALATION = "dcf.escalation.rent"
WAGE_INFLATION = "dcf.escalation.wage"
CONSTRAINT_SHARE = "dcf.incremental.constraint_share"
UPLIFT = "dcf.incremental.uplift"
GP_PER_VEHICLE = "dcf.gp_per_vehicle"


def require(ranges: Mapping[str, ValueRange], key: str) -> ValueRange:
    """Return ``ranges[key]`` or raise a clear error naming the missing range."""
    try:
        return ranges[key]
    except KeyError:
        raise InvalidInputError(
            f"assumptions have no low/base/high range for {key!r}; the scenario layer needs it"
        ) from None


def rent_ratio(ranges: Mapping[str, ValueRange]) -> ValueRange:
    """Return the rent multiplier range: :data:`RENT_RATIO_KEY` if given, else research."""
    return ranges.get(RENT_RATIO_KEY, RENT_RATIO)


def ratio_shock(rng: ValueRange, end: float) -> float:
    """Return ``end / base - 1``: a fractional shock that moves ``base`` to ``end``."""
    if rng.base <= 0:
        raise InvalidInputError(f"range base must be > 0 to form a ratio; got {rng.base!r}")
    return end / rng.base - 1.0


__all__ = [
    "RENT_BASE_PSF_MONTH",
    "RENT_CITATION",
    "RENT_HIGH_PSF_MONTH",
    "RENT_LOW_PSF_MONTH",
    "RENT_RATIO",
    "RENT_RATIO_KEY",
    "ratio_shock",
    "rent_ratio",
    "require",
]
