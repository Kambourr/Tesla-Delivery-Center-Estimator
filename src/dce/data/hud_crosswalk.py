"""HUD–USPS ZIP crosswalk loader.

Contract
--------
Allowlisted host: ``huduser.gov``. ZIP to ZCTA, county, and CBSA. The CBSA
code is what the rent seed joins on. Token: ``HUD_TOKEN`` (Bearer) from the
environment, never from git.

A bundled crosswalk (at least the demo ZIPs, later national or on-demand)
must let rent resolution work offline. Refresh quarterly. Stale after 2
quarters.

Milestone M0: stub. No network calls. M1 resolves ``94402`` from a local fixture.
"""
