"""Top cost drivers.

Contract
--------
``top_drivers(components, n=3) -> list[Driver]``

Rank components by dollars descending and return ``n`` of them.
``share = component / sum(components)``. Shares of the returned list are
each between 0 and 1 and their sum is at most 1.

Pure. No I/O, no network, no LLM.

Milestone M0: raises ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import Driver


def top_drivers(components: dict[str, float], n: int = 3) -> list[Driver]:
    """Return the ``n`` largest components. Not implemented in M0."""
    raise NotImplementedError("dce.model.drivers.top_drivers is a stub (M0)")
