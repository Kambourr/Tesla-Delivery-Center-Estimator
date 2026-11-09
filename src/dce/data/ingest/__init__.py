"""Allowlisted public-data fetchers.

Contract: each module exposes ``fetch_*`` functions that return frozen
dataclasses. They may use the network when a later milestone implements
them. They do not open SQLite and they do not import ``dce.model``
calculation functions. Persistence is ``dce.storage.repository``.

Census ACS, BLS OEWS, the HUD ZIP crosswalk, California DMV counts, the
CEC New ZEV Sales workbook, Census ZCTA gazetteer centroids, and the
ZIP-to-ZCTA crosswalk assembly are implemented. ZCTA cartographic
boundaries can be simplified here. Tesla delivery-center locations load
from a committed snapshot, not from the network. Block groups, QCEW, EIA,
and OpenEI are still stubs and raise ``NotImplementedError``. Nothing here
runs at import time.
"""
