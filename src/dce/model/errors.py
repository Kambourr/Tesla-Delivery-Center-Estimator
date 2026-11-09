"""Typed errors raised by the pure model.

Every error is a :class:`ValueError` so a caller that only knows the
standard library still catches it. Callers that want to tell the cases
apart catch the subclasses.
"""

from __future__ import annotations


class ModelError(ValueError):
    """Base class for every error raised by :mod:`dce.model`."""


class InvalidInputError(ModelError):
    """An input value is missing, non-finite, negative, or out of range."""


class AssumptionsError(InvalidInputError):
    """The assumptions mapping is missing a key or has the wrong shape."""


class ZeroDeliveriesError(InvalidInputError):
    """Cost per delivery was asked for with zero (or fewer) deliveries."""

    def __init__(self, deliveries: float) -> None:
        self.deliveries = deliveries
        super().__init__(
            f"cost per delivery needs estimated annual deliveries > 0; got {deliveries!r}"
        )
