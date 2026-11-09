"""Census ACS 5-year loader (ZCTA and catchment block groups).

Contract
--------
Allowlisted host: ``api.census.gov``. Variables include population
(``B01003_001E``), median household income (``B19013_001E``), vehicles
available, commute, and median home value (``B25077``) for the rent model.
Cache responses in ``zcta_acs`` keyed by geography and year, with ``as_of``.
Refresh annually. Stale if ``as_of`` is older than 18 months.

``fetch_*`` may use ``CENSUS_API_KEY`` from the environment. ``load_*`` reads
SQLite only. No calls at import time.

Milestone M0: no functions that touch the network. This module is a stub.
"""
