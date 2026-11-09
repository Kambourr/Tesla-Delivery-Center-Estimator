"""ZIP-in, estimate-out orchestration.

Contract
--------
``estimate(zip_code, scenario=None, overrides=None) -> EstimateResult``

Load every model input from the bundled seed and the user SQLite database.
Call :func:`dce.data.rent_resolver.resolve_rent` for occupancy cost. Call
only pure functions in ``dce.model``. Optionally write a Folium map and
return its path.

The only required argument is a 5-digit US ZIP (text, so leading zeros
survive). ``overrides`` may later carry an optional advanced rent override.
A missing override must still produce a rent figure. Do not prompt for rent.

Do not import ``dce.extract.pdf_llm``. Do not call an LLM. Do not scrape
listing sites. Same database + ZIP + scenario must yield identical floats.

Milestone M0: ``estimate`` raises ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import EstimateResult, Scenario


def estimate(
    zip_code: str,
    scenario: Scenario | None = None,
    overrides: dict | None = None,
) -> EstimateResult:
    """Run a full estimate for ``zip_code``. Not implemented in M0."""
    raise NotImplementedError("dce.orchestrator.estimate is a stub (M0)")
