"""BLS OEWS wage loader.

Contract
--------
Allowlisted host: ``bls.gov``. Store metro × SOC annual mean and median
wages in ``oews_wage``. Primary occupation is SOC ``49-3023`` (Automotive
Service Technicians and Mechanics); related delivery and admin SOCs may be
added later. Map ZIP to metro with the HUD crosswalk.

Refresh annually (May OEWS). Stale after 18 months. ``BLS_API_KEY`` is
optional for the public API. ``load_*`` reads SQLite only.

Milestone M0: stub. No network calls.
"""
