"""Resolve a US ZIP to county, CBSA, ZCTA, and state.

Contract
--------
``resolve_zip(zip_code) -> GeoContext``

Preserve leading zeros (text, width 5). M1 reads a local HUD fixture for
the San Mateo demo ZIPs ``94401``–``94404`` and returns county ``06081``
plus a CBSA for ``94402``. The fixture path is
``tests/fixtures/hud_9440x.json``. Later milestones read rows the repository
already stored. The HUD download is
:func:`dce.data.ingest.hud_crosswalk.fetch_zip_crosswalk`, not this function.
No network.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import GeoContext


def resolve_zip(zip_code: str) -> GeoContext:
    """Return geographies for a ZIP. Not implemented in M0."""
    raise NotImplementedError("dce.geo.resolve.resolve_zip is a stub (M0)")
