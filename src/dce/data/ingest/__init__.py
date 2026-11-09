"""Allowlisted public-data fetchers.

Contract: each module exposes ``fetch_*`` functions that return frozen
dataclasses. They may use the network when a later milestone implements
them. They do not open SQLite and they do not import ``dce.model``
calculation functions. Persistence is ``dce.storage.repository``.

Census ACS, BLS OEWS, California DMV counts, the CEC New ZEV Sales
workbook, and Census ZCTA gazetteer centroids are implemented. Tesla
delivery-center locations load from a committed snapshot, not from the
network. The other fetchers are still stubs and raise ``NotImplementedError``.
Nothing here runs at import time.
"""
