"""Stored JSON for one ZIP.

A successful row is a ``dce.ui_result.v1`` document from
:func:`dce.app.results.build_ui_result`, plus ``model_version`` and
``inputs_hash``. An unsuccessful row has no schema id. Both are canonical
JSON: sorted keys, no clock, no elapsed time, so two runs match byte for
byte.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from dce.app.results import COMPUTED_AT, build_ui_result
from dce.geo.resolve import ZipResolutionError
from dce.orchestrator import estimate
from dce.precompute.version import MODEL_VERSION, inputs_hash

BAY_AREA_COUNTIES = (
    "06001",  # Alameda
    "06013",  # Contra Costa
    "06041",  # Marin
    "06055",  # Napa
    "06075",  # San Francisco
    "06081",  # San Mateo
    "06085",  # Santa Clara
    "06095",  # Solano
    "06097",  # Sonoma
)


def canonical_json(value: object) -> str:
    """Return compact JSON with sorted keys. NaN and Infinity are rejected."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_estimate_json(zip_code: str) -> str:
    """Return the canonical JSON of ``estimate(zip_code)``."""
    return canonical_json(asdict(estimate(zip_code)))


def payload_for_zip(zip_code: str, *, data_dir: Path | None = None) -> dict[str, object]:
    """Estimate one ZIP. Data gaps become an error document, not a raise."""
    code = zip_code.strip()
    try:
        document = build_ui_result(
            code,
            source="precomputed",
            computed_at=COMPUTED_AT,
            data_dir=data_dir,
        )
    except (ValueError, ZipResolutionError, OSError) as exc:
        return _error(code, exc)
    if document.get("zip_code") != code:
        return _error(
            code,
            ValueError(f"ZIP {code} resolved to {document.get('zip_code')}."),
        )
    document["model_version"] = MODEL_VERSION
    document["inputs_hash"] = inputs_hash()
    return document


def _error(zip_code: str, exc: BaseException) -> dict[str, object]:
    return {
        "zip_code": zip_code,
        "status": "error",
        "reason": f"{type(exc).__name__}: {exc}",
        "model_version": MODEL_VERSION,
        "inputs_hash": inputs_hash(),
        "computed_at": COMPUTED_AT,
    }
