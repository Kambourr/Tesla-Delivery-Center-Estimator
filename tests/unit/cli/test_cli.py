"""CLI: help, a readable estimate, and JSON. No network."""

from __future__ import annotations

import json

import pytest

from dce import __version__
from dce.cli import main


def test_cli_help_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert __version__ == "0.0.0"
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "public data only" in out
    assert "estimate" in out


def test_estimate_94402_prints_both_lenses(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["estimate", "94402"]) == 0
    out = capsys.readouterr().out
    assert "94402" in out
    assert "Cost per delivery" in out
    assert "DCF standalone" in out
    assert "DCF incremental" in out
    assert "Yearly cash flow" in out
    assert "Colma" in out


def test_estimate_json_includes_both_cash_flow_tables(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["estimate", "94402", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["geo"]["zip_code"] == "94402"
    assert payload["catchment"]["gravity"]["deliveries_per_year"] == pytest.approx(5808.3, abs=1)
    assert payload["dcf"]["standalone"]["npv"] > 0
    assert payload["dcf"]["incremental"]["npv"] < 0
    assert len(payload["dcf"]["standalone"]["years"]) == 11
    assert len(payload["dcf"]["incremental"]["years"]) == 11
    assert [driver["name"] for driver in payload["drivers"]] == ["labor", "lease", "capex"]


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "estimate" in out


def test_unknown_zip_exits_with_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["estimate", "00000"]) == 2
    err = capsys.readouterr().err
    assert "00000" in err
