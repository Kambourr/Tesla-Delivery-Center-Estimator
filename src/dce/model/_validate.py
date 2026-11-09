"""Small numeric guards shared by the model modules. Pure."""

from __future__ import annotations

import math

from dce.model.errors import InvalidInputError


def finite(name: str, value: float) -> float:
    """Return ``value`` as a float, or raise if it is not a finite real number."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidInputError(f"{name} must be a number; got {type(value).__name__}")
    out = float(value)
    if not math.isfinite(out):
        raise InvalidInputError(f"{name} must be finite; got {value!r}")
    return out


def non_negative(name: str, value: float) -> float:
    """Return ``value`` if it is finite and ``>= 0``."""
    out = finite(name, value)
    if out < 0:
        raise InvalidInputError(f"{name} must be >= 0; got {value!r}")
    return out


def positive(name: str, value: float) -> float:
    """Return ``value`` if it is finite and ``> 0``."""
    out = finite(name, value)
    if out <= 0:
        raise InvalidInputError(f"{name} must be > 0; got {value!r}")
    return out


def shock(name: str, value: float) -> float:
    """Return a fractional shock if it is finite and ``> -1`` (a cost cannot go negative)."""
    out = finite(name, value)
    if out <= -1.0:
        raise InvalidInputError(f"{name} must be > -1.0 (a -100% shock or worse); got {value!r}")
    return out
