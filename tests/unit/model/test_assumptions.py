"""Strict parsing of the assumptions table."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from dce.model.assumptions import ModelAssumptions, parse_assumptions
from dce.model.errors import AssumptionsError, InvalidInputError, ModelError


def test_shipped_yaml_parses(raw_assumptions: dict[str, Any]) -> None:
    parsed = parse_assumptions(raw_assumptions)
    assert parsed.schema_version == 1
    assert parsed.assumptions_version == "2026.11.0"
    assert parsed.as_of == "2026-11-08"
    assert parsed.facility.sqft == 25_000
    assert parsed.facility.opex_load == pytest.approx(0.15)
    assert parsed.labor.wage_load == pytest.approx(1.30)
    assert parsed.capex.life_years == 10
    assert parsed.demand.base_annual_deliveries == 2_500


def test_parsed_table_passes_through(assumptions: ModelAssumptions) -> None:
    assert parse_assumptions(assumptions) is assumptions


def test_unquoted_yaml_date_is_accepted(raw_assumptions: dict[str, Any]) -> None:
    import datetime

    raw = copy.deepcopy(raw_assumptions)
    raw["as_of"] = datetime.date(2026, 11, 8)
    assert parse_assumptions(raw).as_of == "2026-11-08"


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
        (("schema_version",), 2, "not supported"),
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
