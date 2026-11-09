"""OpenEI Utility Rate Database loader.

Contract
--------
Allowlisted host: ``api.openei.org``. Structured fallback when a hand-parsed
utility schedule is missing. Store energy and demand charges in
``utility_rate`` with ``source='openei'``.

An OpenEI key is intentionally absent from ``.env.example`` until this
loader is implemented. Do not invent a key name in M0.

Milestone M0: stub. No network calls. Not used by the cost model directly;
the orchestrator will read SQLite.
"""
