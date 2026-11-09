"""EIA retail electricity price loader.

Contract
--------
Allowlisted host: ``eia.gov``. Commercial retail ``$/kWh`` by state
(``electricity/retail-sales``). Key: ``EIA_API_KEY``. Store rows in
``utility_rate`` with ``source='eia'``.

Refresh monthly. Stale after 6 months. ``load_*`` reads SQLite only.
Milestone M0: stub. No network calls.
"""
