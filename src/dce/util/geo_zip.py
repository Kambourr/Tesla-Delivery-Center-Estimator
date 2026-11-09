"""Resolve a US ZIP to county, CBSA, ZCTA, and state.

Contract
--------
``resolve_zip(zip_code) -> GeoContext``

Preserve leading zeros (text, width 5). M1 reads a local HUD fixture for
the San Mateo demo ZIPs ``94401``–``94404`` and returns county ``06081``
plus a CBSA for ``94402``. Later milestones read the bundled HUD crosswalk
in SQLite. No network in this function.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import GeoContext


def resolve_zip(zip_code: str) -> GeoContext:
    """Return geographies for a ZIP. Not implemented in M0."""
    raise NotImplementedError("dce.util.geo_zip.resolve_zip is a stub (M0)")
