"""Top-N cost drivers and their shares."""

from __future__ import annotations

import random

import pytest

from dce.model.drivers import top_drivers
from dce.model.errors import InvalidInputError
from dce.model.types import Driver

COMPONENTS = {
    "lease": 300.0,
    "labor": 500.0,
    "utilities": 50.0,
    "property_tax": 25.0,
    "capex": 100.0,
    "other_opex": 25.0,
}


def test_top3_by_dollars() -> None:
    got = top_drivers(COMPONENTS)
    assert got == [
        Driver(name="labor", usd=500.0, share=0.5),
        Driver(name="lease", usd=300.0, share=0.3),
        Driver(name="capex", usd=100.0, share=0.1),
    ]
    assert sum(d.share for d in got) <= 1.0


def test_ties_break_by_name() -> None:
    got = top_drivers(COMPONENTS, n=6)
    assert [d.name for d in got[-2:]] == ["other_opex", "property_tax"]


def test_n_larger_than_components_returns_all() -> None:
    assert len(top_drivers({"lease": 1.0, "labor": 2.0}, n=3)) == 2


def test_n_zero_returns_empty() -> None:
    assert top_drivers(COMPONENTS, n=0) == []


def test_zero_component_is_ranked_with_zero_share() -> None:
    got = top_drivers({"lease": 10.0, "capex": 0.0}, n=2)
    assert got[-1] == Driver(name="capex", usd=0.0, share=0.0)


@pytest.mark.parametrize("seed", range(200))
def test_shares_never_sum_above_one(seed: int) -> None:
    rng = random.Random(seed)
    components = {f"c{i}": rng.uniform(0.0, 1e7) * rng.random() for i in range(6)}
    for n in (1, 3, 6):
        drivers = top_drivers(components, n=n)
        shares = [d.share for d in drivers]
        assert all(0.0 <= s <= 1.0 for s in shares)
        assert sum(shares) <= 1.0
        assert [d.usd for d in drivers] == sorted((d.usd for d in drivers), reverse=True)


def test_all_shares_sum_close_to_one() -> None:
    components = {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.7, "e": 1e-9, "f": 1 / 3}
    shares = [d.share for d in top_drivers(components, n=6)]
    assert sum(shares) <= 1.0
    assert sum(shares) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize(
    ("components", "n", "message"),
    [
        ({}, 3, "empty"),
        ({"lease": 0.0, "labor": 0.0}, 3, "sum to 0"),
        ({"lease": -1.0}, 3, ">= 0"),
        ({"lease": float("nan")}, 3, "finite"),
        ({"lease": 1.0}, -1, "non-negative integer"),
        ({"lease": 1.0}, True, "non-negative integer"),
    ],
)
def test_bad_inputs_raise(components: dict[str, float], n: int, message: str) -> None:
    with pytest.raises(InvalidInputError, match=message):
        top_drivers(components, n=n)
