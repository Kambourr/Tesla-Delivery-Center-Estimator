"""Top cost drivers.

Contract
--------
``top_drivers(components, n=3) -> list[Driver]``

Rank components by dollars descending and return the first ``n`` (all of
them if there are fewer). Ties break by name ascending so the order is
deterministic. ``share = component / sum(components)``.

Every share is in ``[0, 1]`` and the shares of the returned list sum to at
most 1.0 when added left to right with ordinary float addition. Rounding
in the divisions can push that sum one ulp above 1.0 when ``n`` covers
every component; the largest share is then nudged down by the smallest
representable step until the bound holds.

A negative, non-finite, or empty component set, an all-zero total, or a
negative ``n`` raises :class:`~dce.model.errors.InvalidInputError`.

Pure. No I/O, no network, no LLM.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from dce.model import _validate as v
from dce.model.costs import annualized_total
from dce.model.errors import InvalidInputError
from dce.model.types import Driver


def top_drivers(components: Mapping[str, float], n: int = 3) -> list[Driver]:
    """Return the ``n`` largest components with their share of the total."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise InvalidInputError(f"n must be a non-negative integer; got {n!r}")
    total = annualized_total(components)
    if total <= 0:
        raise InvalidInputError("components sum to 0; driver shares are undefined")

    ranked = sorted(
        ((name, v.non_negative(f"components[{name!r}]", usd)) for name, usd in components.items()),
        key=lambda item: (-item[1], item[0]),
    )[:n]
    shares = [min(usd / total, 1.0) for _, usd in ranked]
    _cap_sum_at_one(shares)
    return [
        Driver(name=name, usd=usd, share=share)
        for (name, usd), share in zip(ranked, shares, strict=True)
    ]


def _cap_sum_at_one(shares: list[float]) -> None:
    """Nudge the largest share down until ``sum(shares) <= 1.0``. Mutates ``shares``.

    The largest share is at least ``1 / len(shares)``, so its ulp is close to
    the ulp of 1.0 and the loop ends after a handful of steps. The change is
    a few ulps, far below the 2-decimal reporting precision.
    """
    while shares and sum(shares) > 1.0 and shares[0] > 0.0:
        shares[0] = math.nextafter(shares[0], 0.0)
