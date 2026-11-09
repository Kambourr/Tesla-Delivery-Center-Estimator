"""Read one precomputed dashboard document. No SQLite, and no results table.

The batch command will publish ``get_zip_result(zip)`` and
``get_zip_results(zips)``. The contract for those functions will live in
``docs/contracts/precompute_results.md``. This module calls whichever of
them is importable today:

1. ``dce.precompute.get_zip_result``
2. ``dce.precompute.get_zip_results``
3. ``dce.storage.repository.get_zip_result``
4. ``dce.storage.repository.get_zip_results``

A missing module, a missing function, a raised error, or ``None`` means
there is no row. The caller then computes the ZIP. The return value is
whatever the function returned. :func:`dce.app.api` keeps it only when it
is a ``dce.ui_result.v1`` document for that ZIP.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence

_MODULES = ("dce.precompute", "dce.storage.repository")


def lookup_zip_result(zip_code: str) -> object | None:
    """Return a precomputed payload for ``zip_code``, or ``None``."""
    for module_name in _MODULES:
        module = _module(module_name)
        if module is None:
            continue
        single = getattr(module, "get_zip_result", None)
        if callable(single):
            found = _call(single, zip_code)
            if found is not None:
                return found
        many = getattr(module, "get_zip_results", None)
        if callable(many):
            found = _from_many(_call(many, [zip_code]), zip_code)
            if found is not None:
                return found
    return None


def _module(name: str) -> object | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        return None


def _call(function: object, argument: object) -> object | None:
    try:
        return function(argument)  # type: ignore[operator]
    except Exception:
        return None


def _from_many(payload: object, zip_code: str) -> object | None:
    if isinstance(payload, dict):
        if zip_code in payload:
            return payload[zip_code]
        return payload if payload.get("zip_code") == zip_code else None
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        for item in payload:
            if isinstance(item, dict) and item.get("zip_code") == zip_code:
                return item
    return None
