"""Launch the frozen macOS app and compare two ZIPs with ``estimate()``.

Existing CI skips this file because it does not build the .app. The macOS
app workflow sets ``DCE_FROZEN_BIN`` and ``DCE_REQUIRE_FROZEN=1``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from dce.model.types import EstimateResult
from dce.orchestrator import estimate

_BINARY_ENV = "DCE_FROZEN_BIN"
_REQUIRE_ENV = "DCE_REQUIRE_FROZEN"
_DEFAULT_BIN = Path("dist/DeliveryCenterEstimator.app/Contents/MacOS/DeliveryCenterEstimator")


def _binary() -> Path | None:
    override = os.environ.get(_BINARY_ENV, "").strip()
    path = Path(override) if override else _DEFAULT_BIN
    return path if path.is_file() else None


def test_frozen_app_matches_estimate_for_94402_and_78701(tmp_path: Path) -> None:
    binary = _binary()
    if binary is None:
        if os.environ.get(_REQUIRE_ENV) == "1":
            pytest.fail(f"{_REQUIRE_ENV}=1 but the frozen binary is missing.")
        pytest.skip("Frozen macOS app is not built. make app-bundle produces it.")

    out = tmp_path / "smoke.json"
    env = {key: value for key, value in os.environ.items() if not key.startswith("DCE_RESULTS")}
    env["HOME"] = str(tmp_path / "home")
    env["DCE_SMOKE_OUT"] = str(out)
    proc = subprocess.run(
        [str(binary), "--smoke"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    if proc.returncode != 0 or not out.is_file():
        pytest.fail(
            f"smoke exited {proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["opened_from"] in {"meipass", "application_support"}
    assert report["cold_start_ms"] < 120_000
    rows = report["rows"]
    assert isinstance(rows, dict)
    assert int(rows.get("ok", 0)) + int(rows.get("error", 0)) > 30_000
    clicks = {row["zip"]: row for row in report["clicks"]}
    assert set(clicks) == {"94402", "78701"}
    for zip_code in ("94402", "78701"):
        row = clicks[zip_code]
        assert row["source"] == "precomputed"
        assert 0 <= row["click_ms"] < 3_000
        payload = row["result"]
        assert isinstance(payload, dict)
        _assert_matches_estimate(payload, estimate(zip_code))
    print(
        json.dumps(
            {
                "cold_start_ms": report["cold_start_ms"],
                "click_ms": {zip_code: clicks[zip_code]["click_ms"] for zip_code in clicks},
                "rows": rows,
                "opened_from": report["opened_from"],
            },
            indent=2,
        )
    )


def _assert_matches_estimate(payload: dict[str, object], result: EstimateResult) -> None:
    assert payload["schema"] == "dce.ui_result.v1"
    assert payload["source"] == "precomputed"
    assert payload["zip_code"] == result.geo.zip_code
    assert payload["cost_per_delivery"] == pytest.approx(result.cost_per_delivery)
    assert payload["annualized_total_cost"] == pytest.approx(result.annualized_total_cost)
    assert payload["estimated_annual_deliveries"] == pytest.approx(
        result.estimated_annual_deliveries
    )
    geo = payload["geo"]
    assert isinstance(geo, dict)
    assert geo["zcta"] == result.geo.zcta
    assert geo["county_fips"] == result.geo.county_fips
    assert geo["cbsa"] == result.geo.cbsa
    assert geo["state"] == result.geo.state
    assert result.dcf is not None and result.catchment is not None
    stored_dcf = payload["dcf"]
    assert isinstance(stored_dcf, dict)
    for name in ("standalone", "incremental"):
        stored = stored_dcf[name]
        assert isinstance(stored, dict)
        live = getattr(result.dcf, name)
        assert stored["npv"] == pytest.approx(live.npv)
        _same_optional(stored["irr"], live.irr)
        _same_optional(stored["simple_payback_years"], live.simple_payback_years)
        _same_optional(stored["discounted_payback_years"], live.discounted_payback_years)
    stored_catchment = payload["catchment"]
    assert isinstance(stored_catchment, dict)
    for name in ("gravity", "nearest"):
        stored_case = stored_catchment[name]
        assert isinstance(stored_case, dict)
        live_case = getattr(result.catchment, name)
        assert stored_case["deliveries_per_year"] == pytest.approx(live_case.deliveries_per_year)
    stored_drivers = payload["drivers"]
    assert isinstance(stored_drivers, list)
    assert [row["name"] for row in stored_drivers if isinstance(row, dict)] == [
        driver.name for driver in result.drivers
    ]


def _same_optional(stored: object, live: float | None) -> None:
    if live is None:
        assert stored is None
        return
    assert isinstance(stored, (int, float)) and not isinstance(stored, bool)
    assert stored == pytest.approx(live)
