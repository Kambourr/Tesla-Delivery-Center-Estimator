"""Rank-stability checks across scenarios.

Contract
--------
``spearman_rank_corr(ranks_a, ranks_b) -> float``
    Spearman correlation of two rankings given as ordered labels. Result
    is in ``[-1, 1]``.

``driver_rank_stability(results, baseline_id) -> dict[str, float]``
    For each non-baseline result, Spearman correlation of driver ranks
    against the baseline. A later CLI surfaces the same idea for ZIP
    ``$/delivery`` ranks when several ZIPs are compared.

Pure. No I/O, no network, no LLM.

Milestone M0: both functions raise ``NotImplementedError``.
"""

from __future__ import annotations

from dce.model.types import EstimateResult


def spearman_rank_corr(ranks_a: list[str], ranks_b: list[str]) -> float:
    """Spearman correlation of two label rankings. Not implemented in M0."""
    raise NotImplementedError("dce.scenarios.robustness.spearman_rank_corr is a stub (M0)")


def driver_rank_stability(
    results: list[EstimateResult],
    baseline_id: str,
) -> dict[str, float]:
    """Map scenario id to driver-rank correlation vs baseline. Not implemented in M0."""
    raise NotImplementedError("dce.scenarios.robustness.driver_rank_stability is a stub (M0)")
