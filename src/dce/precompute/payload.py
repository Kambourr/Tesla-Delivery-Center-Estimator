"""Stored JSON for one ZIP.

A successful row is a ``dce.ui_result.v1`` document from
:func:`dce.app.results.build_ui_result`. ``model_version``, ``inputs_hash``,
and ``computed_at`` are columns, and the read API puts them back on the
document. An unsuccessful row has no schema id. Both are canonical JSON:
sorted keys, no clock, no elapsed time, so two runs match byte for byte.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from dce.app.results import COMPUTED_AT, UI_RESULT_SCHEMA, build_ui_result
from dce.geo.resolve import ZipResolutionError
from dce.orchestrator import estimate

# The dashboard does not render ``taken_from``. The stored document keeps the
# largest centers and folds the rest into one total. ``estimate`` still returns
# every center.
TAKEN_FROM_STORED = 8
# Cash-flow table columns. The other year fields stay on ``estimate``.
STORED_YEAR_FIELDS = (
    "year",
    "deliveries",
    "benefit",
    "opex",
    "fcf",
    "cumulative_fcf",
)
# The SVG reads these. The input values at each end are not drawn.
STORED_TORNADO_FIELDS = (
    "driver",
    "label",
    "npv_low",
    "npv_base",
    "npv_high",
    "swing",
)

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
    if document.get("schema") == UI_RESULT_SCHEMA:
        return compact_ui_document(document)
    return _without_row_columns(document)


def compact_ui_document(document: dict[str, object]) -> dict[str, object]:
    """Return the stored dashboard document.

    Headline numbers, the cash-flow columns the table prints, the tornado
    NPV bars, nearby centers, and gravity ZIP shares stay exact. Provenance,
    the year columns the table does not print, per-ZIP delivery amounts, the
    nearest-center ZIP list, tornado input values, scenario fields the cards
    do not print, and the tail of ``taken_from`` are omitted. ``estimate``
    still returns those.
    """
    stored = _without_row_columns(document)
    catchment = document.get("catchment")
    if isinstance(catchment, dict):
        stored["catchment"] = _compact_catchment(catchment)
    dcf = document.get("dcf")
    if isinstance(dcf, dict):
        stored["dcf"] = {
            name: _compact_lens(lens) if isinstance(lens, dict) else lens
            for name, lens in dcf.items()
        }
    tornado = document.get("tornado")
    if isinstance(tornado, list):
        stored["tornado"] = _compact_tornado(tornado)
    scenarios = document.get("scenarios")
    if isinstance(scenarios, dict):
        stored["scenarios"] = _compact_scenarios(scenarios)
    return stored


def _compact_catchment(catchment: dict[str, object]) -> dict[str, object]:
    compact = dict(catchment)
    gravity = catchment.get("gravity")
    if isinstance(gravity, dict):
        compact["gravity"] = _compact_case(gravity, keep_zips=True)
    nearest = catchment.get("nearest")
    if isinstance(nearest, dict):
        # The map paints gravity shares. The nearest total stays; its ZIP list does not.
        compact["nearest"] = _compact_case(nearest, keep_zips=False)
    return compact


def _compact_case(case: dict[str, object], *, keep_zips: bool) -> dict[str, object]:
    compact = dict(case)
    if keep_zips:
        zips = case.get("zips")
        if isinstance(zips, list):
            compact["zips"] = [
                {"zip_code": row["zip_code"], "share": row["share"]}
                for row in zips
                if isinstance(row, dict) and "zip_code" in row and "share" in row
            ]
    else:
        compact["zips"] = []
    taken = case.get("taken_from")
    if isinstance(taken, list):
        compact["taken_from"] = _compact_taken(taken)
    return compact


def _compact_taken(rows: list[object]) -> list[dict[str, object]]:
    centers = [row for row in rows if isinstance(row, dict)]
    kept = [dict(row) for row in centers[:TAKEN_FROM_STORED]]
    rest = centers[TAKEN_FROM_STORED:]
    if not rest:
        return kept
    other = math.fsum(_taken_amount(row) for row in rest)
    kept.append(
        {
            "center_id": "other",
            "name": "Other centers",
            "deliveries_per_year": other,
        }
    )
    return kept


def _taken_amount(row: dict[str, object]) -> float:
    value = row.get("deliveries_per_year")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def _compact_tornado(rows: list[object]) -> list[dict[str, object]]:
    compact: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        compact.append({field: row[field] for field in STORED_TORNADO_FIELDS if field in row})
    return compact


def _compact_scenarios(scenarios: dict[str, object]) -> dict[str, object]:
    compact: dict[str, object] = {}
    for name, card in scenarios.items():
        if not isinstance(card, dict):
            compact[name] = card
            continue
        standalone = card.get("standalone")
        kept_standalone: dict[str, object] = {}
        if isinstance(standalone, dict):
            kept_standalone = {
                field: standalone[field] for field in ("npv", "irr") if field in standalone
            }
        compact[name] = {
            "scenario_id": card.get("scenario_id", name),
            "label": card.get("label"),
            "cost_per_delivery": card.get("cost_per_delivery"),
            "standalone": kept_standalone,
        }
    return compact


def _compact_lens(lens: dict[str, object]) -> dict[str, object]:
    compact = dict(lens)
    years = lens.get("years")
    if isinstance(years, list):
        compact["years"] = [
            {field: row[field] for field in STORED_YEAR_FIELDS if field in row}
            for row in years
            if isinstance(row, dict)
        ]
    return compact


def _without_row_columns(document: dict[str, object]) -> dict[str, object]:
    """Drop fields that ``zip_result`` already stores as columns.

    ``get_zip_result`` puts ``model_version``, ``inputs_hash``, and
    ``computed_at`` back on the document it returns.
    """
    return {
        key: value
        for key, value in document.items()
        if key not in {"provenance", "model_version", "inputs_hash", "computed_at"}
    }


def _error(zip_code: str, exc: BaseException) -> dict[str, object]:
    return {
        "zip_code": zip_code,
        "status": "error",
        "reason": f"{type(exc).__name__}: {exc}",
    }
