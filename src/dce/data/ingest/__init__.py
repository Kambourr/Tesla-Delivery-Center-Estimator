"""Allowlisted public-data fetchers.

Contract: each module exposes ``fetch_*`` functions that return frozen
dataclasses. They may use the network when a later milestone implements
them. They do not open SQLite and they do not import ``dce.model``
calculation functions. Persistence is ``dce.storage.repository``.

Census ACS, BLS OEWS, the HUD ZIP crosswalk, California DMV counts, the
CEC New ZEV Sales workbook, Census ZCTA gazetteer centroids, the
ZIP-to-ZCTA crosswalk assembly, EIA Table 5.6.A, and one OpenEI URDB
schedule are implemented. ZCTA cartographic boundaries can be simplified
here. Tesla delivery-center locations load from a committed snapshot, not
from the network. Block groups and QCEW are still stubs and raise
``NotImplementedError``. ``estimate`` does not call the fetchers. Nothing
here runs at import time.
"""
