"""NPV tornado on the San Mateo fixtures (dcf_design.md §4 tornado table)."""

from __future__ import annotations

import dataclasses
import json

import pytest
from scenario_data import STEADY

from dce.model.assumptions import ModelAssumptions, ValueRange
from dce.model.dcf import build_dcf_inputs, run_dcf
from dce.model.errors import InvalidInputError
from dce.model.types import CostInputs, Scenario
from dce.scenarios import ranges as r
from dce.scenarios.tornado import TornadoInputs, dcf_tornado, tornado_rows
from dce.scenarios.types import TornadoBar

# dcf_design.md §4, standalone NPV in $M: driver -> (input, NPV) at each end,
# bad end first. Deliveries is left out: the research bar runs 3,000 to 5,700
# absolute, while this layer scales the volume by 3,000 / 4,500 and 6,500 / 4,500.
RESEARCH_TORNADO = {
    "fee": ((1_250, 7.2), (1_640, 14.1)),
    "inbound_freight": ((343, 6.3), (75, 11.0)),
    "deliveries_per_fte": ((200, 7.0), (450, 11.3)),
    "wacc": ((0.163, 8.3), (0.097, 12.2)),
    "growth": ((0.0, 8.0), (0.10, 10.9)),
    "fitout": ((160, 8.3), (60, 10.6)),
    "wage": ((31.09, 8.6), (20.73, 10.8)),
    "rent": ((2.95, 8.4), (1.74, 10.3)),
}

# This layer's full standalone tornado at 4,400 deliveries, $M:
# driver -> (npv_low, npv_high), largest swing first.
GOLDEN_TORNADO = [
    ("deliveries", 3.930, 17.063),
    ("fee", 7.190, 14.119),
    ("inbound_freight", 6.249, 11.010),
    ("horizon", 7.894, 12.647),
    ("deliveries_per_fte", 6.971, 11.273),
    ("wacc", 8.300, 12.160),
    ("growth", 8.027, 10.929),
    ("fitout", 8.299, 10.597),
    ("wage", 8.673, 10.682),
    ("rent", 8.470, 10.274),
    ("ramp", 8.984, 10.177),
    ("equipment", 9.364, 9.887),
    ("wage_load", 9.357, 9.878),
    ("wage_inflation", 9.480, 9.804),
    ("min_headcount", 9.364, 9.678),
    ("rent_escalation", 9.615, 9.739),
]

BASE_NPV = 9.678e6


@pytest.fixture
def bars(tornado_inputs: TornadoInputs) -> list[TornadoBar]:
    return dcf_tornado(tornado_inputs)


def test_deliveries_rank_first_and_bars_sort_by_swing(bars: list[TornadoBar]) -> None:
    assert bars[0].driver == "deliveries"
    swings = [bar.swing for bar in bars]
    assert swings == sorted(swings, reverse=True)
    assert all(bar.swing == pytest.approx(bar.npv_high - bar.npv_low) for bar in bars)


def test_every_bar_brackets_the_base_npv(bars: list[TornadoBar]) -> None:
    for bar in bars:
        assert bar.npv_base == pytest.approx(BASE_NPV, abs=0.005e6)
        assert bar.npv_low <= bar.npv_base + 1e-6 <= bar.npv_high + 2e-6, bar.driver


def test_base_npv_is_the_model_npv(
    bars: list[TornadoBar],
    costs: CostInputs,
    assumptions: ModelAssumptions,
    baseline: Scenario,
) -> None:
    direct = run_dcf(
        costs,
        build_dcf_inputs(assumptions),
        assumptions,
        steady_deliveries=STEADY,
        scenario=baseline,
    )
    assert {bar.npv_base for bar in bars} == {direct.npv}


@pytest.mark.parametrize("driver", sorted(RESEARCH_TORNADO))
def test_matches_research_tornado(bars: list[TornadoBar], driver: str) -> None:
    """Published bars are rounded to $0.1M; allow $0.15M."""
    bar = next(b for b in bars if b.driver == driver)
    (bad_input, bad_npv), (good_input, good_npv) = RESEARCH_TORNADO[driver]
    assert bar.input_at_npv_low == pytest.approx(bad_input, rel=1e-6)
    assert bar.input_at_npv_high == pytest.approx(good_input, rel=1e-6)
    assert bar.npv_low == pytest.approx(bad_npv * 1e6, abs=0.15e6)
    assert bar.npv_high == pytest.approx(good_npv * 1e6, abs=0.15e6)


def test_golden_tornado(bars: list[TornadoBar]) -> None:
    assert [bar.driver for bar in bars] == [row[0] for row in GOLDEN_TORNADO]
    for bar, (_driver, low, high) in zip(bars, GOLDEN_TORNADO, strict=True):
        assert bar.npv_low == pytest.approx(low * 1e6, abs=0.005e6), bar.driver
        assert bar.npv_high == pytest.approx(high * 1e6, abs=0.005e6), bar.driver


def test_ratio_driver_inputs_scale_the_resolved_values(bars: list[TornadoBar]) -> None:
    by = {bar.driver: bar for bar in bars}
    assert by["deliveries"].input_base == STEADY
    assert by["deliveries"].input_at_npv_low == pytest.approx(STEADY * 3_000 / 4_500)
    assert by["deliveries"].input_at_npv_high == pytest.approx(STEADY * 6_500 / 4_500)
    assert by["rent"].input_base == pytest.approx(2.14)
    assert by["wage"].input_base == pytest.approx(25.91)
    assert by["horizon"].input_at_npv_low == 8
    assert by["horizon"].input_at_npv_high == 15
    assert by["ramp"].input_at_npv_low == 0.60
    assert by["ramp"].input_at_npv_high == 0.90


def test_rows_are_plain_json_data(bars: list[TornadoBar]) -> None:
    rows = tornado_rows(bars)
    assert len(rows) == len(bars)
    assert rows[0]["driver"] == "deliveries"
    assert set(rows[0]) == {f.name for f in dataclasses.fields(TornadoBar)}
    assert json.loads(json.dumps(rows)) == rows


def test_rent_multiplier_range_replaces_the_research_ratios(
    tornado_inputs: TornadoInputs, assumptions: ModelAssumptions
) -> None:
    flat = {**assumptions.ranges, r.RENT_RATIO_KEY: ValueRange(1.0, 1.0, 1.0)}
    rent = next(b for b in dcf_tornado(tornado_inputs, flat) if b.driver == "rent")
    assert rent.swing == 0.0


def test_tornado_respects_a_shocked_base_case(
    tornado_inputs: TornadoInputs, baseline: Scenario
) -> None:
    shocked = dataclasses.replace(
        tornado_inputs, scenario=dataclasses.replace(baseline, wage_shock=0.1)
    )
    bars = dcf_tornado(shocked)
    wage = next(b for b in bars if b.driver == "wage")
    assert wage.input_base == pytest.approx(25.91 * 1.1)
    assert all(b.npv_base < BASE_NPV for b in bars)


def test_incremental_lens_adds_its_drivers(tornado_inputs: TornadoInputs) -> None:
    bars = dcf_tornado(dataclasses.replace(tornado_inputs, benefit_mode="incremental"))
    drivers = {bar.driver for bar in bars}
    assert {"constraint_share", "uplift", "gp_per_vehicle"} <= drivers
    assert bars[0].npv_base == pytest.approx(-2.65e6, abs=0.01e6)
    assert bars[0].driver == "constraint_share"
    # The incremental ramp bar is not monotone on these inputs: both ends sit
    # about $15k-$18k below base. Bars still span their two end NPVs.
    for bar in bars:
        assert bar.npv_low <= bar.npv_high, bar.driver


def test_missing_range_raises(tornado_inputs: TornadoInputs, assumptions: ModelAssumptions) -> None:
    trimmed = {k: v for k, v in assumptions.ranges.items() if k != r.FEE}
    with pytest.raises(InvalidInputError, match="fee_per_delivery"):
        dcf_tornado(tornado_inputs, trimmed)
