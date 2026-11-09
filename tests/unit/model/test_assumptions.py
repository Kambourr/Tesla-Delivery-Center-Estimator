"""Strict parsing of the assumptions table."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from dce.model.assumptions import ModelAssumptions, ValueRange, parse_assumptions
from dce.model.errors import AssumptionsError, InvalidInputError, ModelError


def test_shipped_yaml_parses(raw_assumptions: dict[str, Any]) -> None:
    parsed = parse_assumptions(raw_assumptions)
    assert parsed.schema_version == 2
    assert parsed.assumptions_version == "2026.11.1"
    assert parsed.as_of == "2026-11-08"
    assert parsed.facility.sqft == 25_000
    assert parsed.facility.opex_load == pytest.approx(0.15)
    assert parsed.labor.wage_load == pytest.approx(1.35)
    assert parsed.labor.staffing.min_headcount == 10
    assert parsed.labor.staffing.deliveries_per_fte == 300
    assert parsed.capex.life_years == 10
    assert parsed.property_tax.included_in_nnn is True
    assert parsed.demand.base_annual_deliveries == 4_500
    assert parsed.dcf.discount_rate == pytest.approx(0.136)
    assert parsed.dcf.benefit_mode == "standalone"
    assert parsed.dcf.horizon_years == 10
    assert parsed.dcf.ramp == (0.75, 0.95, 1.0)


def test_ranges_keep_low_base_high(raw_assumptions: dict[str, Any]) -> None:
    ranges = parse_assumptions(raw_assumptions).ranges
    assert ranges["dcf.discount_rate"] == ValueRange(low=0.097, base=0.136, high=0.163)
    assert ranges["demand.base_annual_deliveries"] == ValueRange(3_000, 4_500, 6_500)
    assert ranges["labor.wage_load"] == ValueRange(1.30, 1.35, 1.43)
    assert ranges["labor.staffing.deliveries_per_fte"] == ValueRange(200, 300, 450)
    assert "facility.opex_load" not in ranges  # a plain number has no range


def test_mixes_and_seasonality(raw_assumptions: dict[str, Any]) -> None:
    parsed = parse_assumptions(raw_assumptions)
    assert parsed.vehicle_mix["model_y"] == pytest.approx(0.70)
    assert sum(parsed.vehicle_mix.values()) == pytest.approx(1.0)
    assert [e.socs for e in parsed.labor.wage_mix] == [
        ("41-2031",),
        ("53-7061",),
        ("53-7062", "53-7065"),
        ("41-1011",),
    ]
    assert parsed.seasonality.quarter_shares == (0.23, 0.26, 0.28, 0.23)
    assert parsed.seasonality.month_in_quarter == (0.25, 0.30, 0.45)
    assert parsed.seasonality.month_in_quarter_high == (0.20, 0.25, 0.55)


def test_parsed_table_passes_through(assumptions: ModelAssumptions) -> None:
    assert parse_assumptions(assumptions) is assumptions


def test_unquoted_yaml_date_is_accepted(raw_assumptions: dict[str, Any]) -> None:
    import datetime

    raw = copy.deepcopy(raw_assumptions)
    raw["as_of"] = datetime.date(2026, 11, 8)
    assert parse_assumptions(raw).as_of == "2026-11-08"


def test_plain_number_is_accepted_where_a_range_is_shipped(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    raw["dcf"]["discount_rate"] = 0.10
    parsed = parse_assumptions(raw)
    assert parsed.dcf.discount_rate == 0.10
    assert "dcf.discount_rate" not in parsed.ranges


def _mutated(raw: dict[str, Any], path: tuple[str, ...], value: object) -> dict[str, Any]:
    out = copy.deepcopy(raw)
    node = out
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return out


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("schema_version",), 1, "not supported"),
        (("schema_version",), "1", "integer"),
        (("facility", "sqft"), 0, "> 0"),
        (("facility", "sqft"), "25000", "number"),
        (("facility", "opex_load"), -0.1, ">= 0"),
        (("labor", "wage_load"), 0.30, "multiplier"),
        (("labor", "staffing", "deliveries_per_fte"), 0, "> 0"),
        (("capex", "life_years"), 0, "> 0"),
        (("demand", "factors", "ev_share", "reference"), 0, "> 0"),
        (("demand", "factors", "ev_share", "elasticity"), float("nan"), "finite"),
        (("demand", "score_min"), 5.0, "must not exceed"),
        (("demand", "factors"), [], "mapping"),
        (("assumptions_version",), "  ", "empty"),
        (("assumptions_version",), 3, "text"),
        (("facility", "sqft"), True, "number"),
        (("labor", "wage_load"), {"low": 0.9, "base": 1.35, "high": 1.43}, "multiplier"),
        (("dcf", "discount_rate"), {"low": 0.2, "base": 0.136, "high": 0.163}, "low <= base"),
        (("dcf", "discount_rate"), {"low": 0.1, "base": 0.136}, "missing"),
        (("dcf", "horizon_years"), 9.5, "whole number"),
        (("dcf", "benefit_mode"), "npv", "one of"),
        (("dcf", "terminal", "mode"), "forever", "one of"),
        (("dcf", "incremental", "constraint_share"), 1.5, "<= 1"),
        (("dcf", "incremental", "overtime_multiplier"), 0.5, ">= 1"),
        (("dcf", "volume", "ramp"), {"low": [1], "base": [1, 1], "high": [1]}, "same length"),
        (("dcf", "volume", "ramp"), [1.0], "mapping"),
        (("vehicle_mix", "model_y"), 0.5, "sum to 1"),
        (("seasonality", "quarter_shares"), [0.25, 0.25, 0.25], "4 values"),
        (("seasonality", "quarter_shares"), [0.3, 0.3, 0.3, 0.3], "sum to 1"),
        (("labor", "wage_mix"), [], "non-empty list"),
        (("property_tax", "included_in_nnn"), "yes", "true or false"),
    ],
)
def test_bad_values_raise_assumptions_error(
    raw_assumptions: dict[str, Any], path: tuple[str, ...], value: object, message: str
) -> None:
    with pytest.raises(AssumptionsError, match=message):
        parse_assumptions(_mutated(raw_assumptions, path, value))


def test_missing_key_is_reported(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    del raw["capex"]["fitout_psf"]
    with pytest.raises(AssumptionsError, match=r"capex is missing \['fitout_psf'\]"):
        parse_assumptions(raw)


def test_unknown_key_is_reported(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    raw["facility"]["sqft_typo"] = 1
    with pytest.raises(AssumptionsError, match="unknown keys"):
        parse_assumptions(raw)


def test_root_must_be_a_mapping() -> None:
    with pytest.raises(AssumptionsError, match="mapping"):
        parse_assumptions([])  # type: ignore[arg-type]


def test_error_hierarchy() -> None:
    assert issubclass(AssumptionsError, InvalidInputError)
    assert issubclass(InvalidInputError, ModelError)
    assert issubclass(ModelError, ValueError)


def test_renewal_growth_must_be_below_discount_rate(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    raw["dcf"]["terminal"] = {"mode": "renewal", "growth": 0.20}
    with pytest.raises(AssumptionsError, match="below dcf.discount_rate"):
        parse_assumptions(raw)


def test_bad_soc_code_is_reported(raw_assumptions: dict[str, Any]) -> None:
    raw = copy.deepcopy(raw_assumptions)
    raw["labor"]["wage_mix"][0]["socs"] = ["412031"]
    with pytest.raises(AssumptionsError, match="expected a code like"):
        parse_assumptions(raw)
