"""BLS QCEW county industry-wage loader.

Contract
--------
Allowlisted host: ``bls.gov``. QCEW is NAICS, not SOC. Use auto-dealer and
repair industries as a county scaler against the OEWS metro occupation wage.
Do not treat QCEW as a substitute for SOC ``49-3023``.

Refresh quarterly. Stale after 4 quarters. Reads and writes SQLite.
Milestone M0: stub. No network calls.
"""
