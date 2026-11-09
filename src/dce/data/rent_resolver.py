"""Automatic commercial rent for one ZIP.

Contract
--------
``resolve_rent(zip_code, conn) -> RentResolution``

The user does not type rent. Read SQLite / the bundled seed only. No HTTP,
no LLM, and no LoopNet, Crexi, CoStar, CompStak, Reonomy, ATTOM, or Cherre.

Fallback chain, first hit wins:

1. ZIP-adjusted CBSA industrial: broker seed times a frozen ACS model
   (income, density, median home value) calibrated offline on the GSA
   Lease Inventory. Confidence high or medium.
2. County median of GSA $/SF (industrial-leaning filter when present),
   with the same ACS adjustment.
3. Raw CBSA industrial seed (no ZIP adjustment).
4. State median industrial seed or GSA.
5. National industrial default from the seed.
6. HUD SAFMR (2-bedroom) or ZORI times a commercial-to-residential ratio.
   Confidence ``low``. The result must be flagged low-confidence.

ZIP maps to CBSA through the HUD crosswalk. Property type for the
delivery-center narrative is industrial / flex. If the only local comps
are office GSA leases, down-weight them and lower confidence.

Write the chosen row to ``rent_resolved_cache``. An optional advanced
override, if the orchestrator passes one, replaces the resolved dollars
but does not change this chain's existence: ZIP alone must still resolve.

Milestone M0: the dataclass is the contract; ``resolve_rent`` raises
``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RentResolution:
    """Resolved asking rent for one ZIP. M0 never constructs this from data."""

    zip_code: str
    rent_psf_year: float
    rent_psf_month: float
    property_type: str
    tier: str
    confidence: str
    as_of: str
    citation: str


def resolve_rent(zip_code: str, conn: object) -> RentResolution:
    """Resolve industrial asking rent from SQLite only. Not implemented in M0."""
    raise NotImplementedError("dce.data.rent_resolver.resolve_rent is a stub (M0)")
