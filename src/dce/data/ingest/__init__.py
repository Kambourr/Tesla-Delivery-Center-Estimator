"""Allowlisted public-data fetchers.

Contract: each module exposes ``fetch_*`` functions that return frozen
dataclasses. They may use the network when a later milestone implements
them. They do not open SQLite and they do not import ``dce.model``
calculation functions. Persistence is ``dce.storage.repository``.

M2 implements Census ACS, BLS OEWS, and California DMV vehicle counts.
The other fetchers are still stubs and raise ``NotImplementedError``.
Nothing here runs at import time.
"""
