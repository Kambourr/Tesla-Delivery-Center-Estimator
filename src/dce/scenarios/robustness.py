"""Rank-stability checks across scenarios.

Contract
--------
``spearman_rank_corr(ranks_a, ranks_b) -> float``
    Spearman correlation of two rankings of the same labels, each given as
    labels in rank order (first = rank 1). Result is in ``[-1, 1]``; fewer
    than two labels is ``1.0`` (nothing can reorder).

``component_ranking(result) -> list[str]``
    Every cost component of one estimate, largest dollars first (ties by
    name). Ranking all components, not only the top 3, keeps the label sets
    equal across scenarios.

``driver_rank_stability(results, baseline_id) -> dict[str, float]``
    For each non-baseline :class:`ScenarioResult`, Spearman correlation of its
    cost-component ranking against the baseline's.

``tornado_ranking(bars) -> list[str]`` and
``npv_driver_rank_stability(tornados, baseline_id) -> dict[str, float]``
    The same check for NPV drivers: each tornado ranks drivers by swing.

Pure. No I/O, no network, no LLM.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from dce.model.errors import InvalidInputError
from dce.model.types import EstimateResult
from dce.scenarios.types import ScenarioResult, TornadoBar

_T = TypeVar("_T")


def spearman_rank_corr(ranks_a: Sequence[str], ranks_b: Sequence[str]) -> float:
    """Return ``1 - 6 Σ d² / (n (n² - 1))`` for two orderings of the same labels."""
    a, b = list(ranks_a), list(ranks_b)
    for name, ranking in (("ranks_a", a), ("ranks_b", b)):
        if len(set(ranking)) != len(ranking):
            raise InvalidInputError(f"{name} repeats a label: {ranking}")
    if set(a) != set(b):
        raise InvalidInputError(
            f"rankings must hold the same labels; only in a: {sorted(set(a) - set(b))}, "
            f"only in b: {sorted(set(b) - set(a))}"
        )
    n = len(a)
    if n < 2:
        return 1.0
    position = {label: i for i, label in enumerate(b)}
    d2 = sum((i - position[label]) ** 2 for i, label in enumerate(a))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def component_ranking(result: EstimateResult) -> list[str]:
    """Return component names ordered by dollars, largest first (ties by name)."""
    return sorted(result.components, key=lambda name: (-result.components[name], name))


def driver_rank_stability(
    results: Sequence[ScenarioResult],
    baseline_id: str,
) -> dict[str, float]:
    """Map each non-baseline scenario id to its component-rank Spearman vs baseline."""
    by_id = _unique({res.scenario_id: res for res in results}, [r.scenario_id for r in results])
    baseline = _baseline(by_id, baseline_id)
    reference = component_ranking(baseline.result)
    return {
        sid: spearman_rank_corr(reference, component_ranking(res.result))
        for sid, res in by_id.items()
        if sid != baseline_id
    }


def tornado_ranking(bars: Sequence[TornadoBar]) -> list[str]:
    """Return driver ids ordered by swing, largest first (ties by driver id)."""
    return [bar.driver for bar in sorted(bars, key=lambda bar: (-bar.swing, bar.driver))]


def npv_driver_rank_stability(
    tornados: Mapping[str, Sequence[TornadoBar]],
    baseline_id: str,
) -> dict[str, float]:
    """Map each non-baseline scenario id to its NPV-driver Spearman vs baseline."""
    reference = tornado_ranking(_baseline(tornados, baseline_id))
    return {
        sid: spearman_rank_corr(reference, tornado_ranking(bars))
        for sid, bars in tornados.items()
        if sid != baseline_id
    }


def _unique(by_id: dict[str, ScenarioResult], ids: list[str]) -> dict[str, ScenarioResult]:
    if len(by_id) != len(ids):
        repeated = sorted({sid for sid in ids if ids.count(sid) > 1})
        raise InvalidInputError(f"scenario ids must be unique; repeated: {repeated}")
    return by_id


def _baseline(items: Mapping[str, _T], baseline_id: str) -> _T:
    try:
        return items[baseline_id]
    except KeyError:
        raise InvalidInputError(
            f"baseline {baseline_id!r} is not among the scenarios: {sorted(items)}"
        ) from None


__all__ = [
    "component_ranking",
    "driver_rank_stability",
    "npv_driver_rank_stability",
    "spearman_rank_corr",
    "tornado_ranking",
]
