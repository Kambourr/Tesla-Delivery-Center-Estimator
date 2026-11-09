"""Precomputed ZIP results for an instant map click.

``precompute`` runs :func:`dce.orchestrator.evaluate_zip` for every resolvable
ZIP and stores the JSON document described in
``docs/contracts/precompute_results.md``. ``get_zip_result`` and
``get_zip_results`` only read that table.
"""

from dce.precompute.run import (
    PrecomputeReport,
    format_report,
    get_zip_result,
    get_zip_results,
    precompute,
    result_counts,
)
from dce.precompute.version import MODEL_VERSION, inputs_hash

__all__ = [
    "MODEL_VERSION",
    "PrecomputeReport",
    "format_report",
    "get_zip_result",
    "get_zip_results",
    "inputs_hash",
    "precompute",
    "result_counts",
]
