"""Allowlisted public-data fetchers.

Contract: each module exposes ``fetch_*`` functions that return frozen
dataclasses. They may use the network when a later milestone implements
them. They do not open SQLite and they do not import ``dce.model``
calculation functions. Persistence is ``dce.storage.repository``.

Milestone M0: every ``fetch_*`` raises ``NotImplementedError`` and nothing
here runs at import time.
"""
