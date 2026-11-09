"""California ZEV / fuel-type counts by ZIP.

Contract
--------
Allowlisted hosts: ``energy.ca.gov`` (CEC light-duty vehicle population) and
``data.ca.gov`` (DMV fuel type by ZIP). Upsert ``ev_zip`` with
``source`` of ``cec``, ``dmv``, or ``fallback``.

Outside California, use DOE AFDC or state open data where available;
otherwise an ACS plus national EV-share proxy flagged
``ev_proxy=acs_national_fallback``. Refresh about annually. Stale after 18
months. No API key for the file downloads.

Milestone M0: stub. No network calls.
"""
