"""End-to-end San Mateo estimate. Fixtures only: no network."""

from __future__ import annotations

import pytest
import yaml

from dce.config import assumptions_path
from dce.model.assumptions import parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.dcf import run_dcf_views
from dce.model.types import Scenario
from dce.orchestrator import EstimateDataError, estimate

# Research illustrative case (dcf_design.md §4) uses 4,400 steady deliveries,
# the nearest-center figure rounded. This pipeline feeds gravity instead.
RESEARCH_STEADY = 4_400.0
RENT = 2.14
ENERGY = 0.2875
DEMAND_RATE = 20.50


def _research_views(steady: float) -> tuple[float, float | None, float | None, float | None, float]:
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assumptions = parse_assumptions(raw)
    scenario = Scenario(vehicle_mix=dict(assumptions.vehicle_mix), wage_shock=0.0)
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=RENT,
        wage_annual=assumptions.labor.fallback_wage_hourly * assumptions.labor.paid_hours_per_fte,
        energy_rate_kwh=ENERGY,
        demand_rate_kw=DEMAND_RATE,
        annual_deliveries=steady,
    )
    views = run_dcf_views(costs, assumptions, steady_deliveries=steady, scenario=scenario)
    standalone = views.standalone
    return (
        standalone.npv,
        standalone.irr,
        standalone.simple_payback_years,
        standalone.discounted_payback_years,
        views.incremental.npv,
    )


def test_estimate_94402_matches_research_adjusted_for_gravity_volume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gravity volume, $/delivery, and both DCF views. No sockets.

    The published standalone case is NPV +$9.7M, IRR about 66%, simple
    payback about 1.7 years, at 4,400 deliveries. Incremental is about
    −$2.8M. Substituting the gravity volume this run actually produces
    (about 5,523) raises the standalone NPV, IRR, and shortens payback.
    Incremental stays near −$2.8M because that lens scales cost and benefit
    together. The dollar checks below are that adjusted case.
    """

    def fail(url: str, **_kwargs: object) -> object:
        raise AssertionError(f"estimate must not fetch {url}")

    monkeypatch.setattr("dce.data.ingest.http.request_bytes", fail)
    monkeypatch.setattr("dce.data.ingest.http.request_json", fail)

    result = estimate("94402")
    assert result.catchment is not None
    assert result.dcf is not None
    gravity = result.catchment.gravity.deliveries_per_year
    nearest = result.catchment.nearest.deliveries_per_year
    assert nearest == pytest.approx(4370, abs=1)
    assert gravity == pytest.approx(5522.8, abs=1)
    assert result.estimated_annual_deliveries == pytest.approx(gravity)
    assert [row.center_id for row in result.catchment.gravity.taken_from[:2]] == [
        "colma",
        "sunnyvale",
    ]
    assert result.catchment.nearest.zips
    assert len(result.catchment.nearest.zips) == 20
    taken = sum(row.deliveries_per_year for row in result.catchment.gravity.taken_from)
    assert taken == pytest.approx(gravity, abs=1)

    assert [driver.name for driver in result.drivers] == ["labor", "lease", "capex"]
    assert result.cost_per_delivery == pytest.approx(500.94, abs=0.05)
    assert result.dcf.standalone.discount_rate == pytest.approx(0.136)
    assert result.map_path is None

    anchor_npv, anchor_irr, anchor_payback, _anchor_disc, anchor_incremental = _research_views(
        RESEARCH_STEADY
    )
    assert anchor_npv == pytest.approx(9.7e6, abs=0.1e6)
    assert anchor_irr == pytest.approx(0.66, abs=0.01)
    assert anchor_payback == pytest.approx(1.7, abs=0.05)
    assert anchor_incremental == pytest.approx(-2.8e6, abs=0.25e6)

    adjusted_npv, adjusted_irr, adjusted_payback, adjusted_disc, adjusted_incremental = (
        _research_views(gravity)
    )
    standalone = result.dcf.standalone
    incremental = result.dcf.incremental
    assert standalone.npv == pytest.approx(adjusted_npv, abs=1.0)
    assert standalone.irr == pytest.approx(adjusted_irr, abs=1e-9)
    assert standalone.simple_payback_years == pytest.approx(adjusted_payback, abs=1e-9)
    assert standalone.discounted_payback_years == pytest.approx(adjusted_disc, abs=1e-9)
    assert incremental.npv == pytest.approx(adjusted_incremental, abs=1.0)
    assert incremental.simple_payback_years is None
    assert incremental.discounted_payback_years is None

    # Gravity 5,523 versus the research case at 4,400. These are the adjusted
    # figures the pipeline must keep producing.
    assert standalone.npv == pytest.approx(13.92e6, abs=0.05e6)
    assert standalone.irr == pytest.approx(0.858, abs=0.01)
    assert standalone.simple_payback_years == pytest.approx(1.31, abs=0.05)
    assert standalone.discounted_payback_years == pytest.approx(1.51, abs=0.05)
    assert incremental.npv == pytest.approx(-2.62e6, abs=0.05e6)
    assert incremental.npv == pytest.approx(-2.8e6, abs=0.25e6)
    assert len(standalone.years) == 11
    assert standalone.years[0].capex == pytest.approx(3_780_000)


def test_rent_override_is_optional_and_checked() -> None:
    base = estimate("94402")
    cheaper = estimate("94402", overrides={"rent_psf_month": 0})
    assert cheaper.cost_per_delivery < base.cost_per_delivery
    assert cheaper.dcf is not None and base.dcf is not None
    assert cheaper.dcf.standalone.npv != base.dcf.standalone.npv
    with pytest.raises(EstimateDataError, match="rent_psf_month"):
        estimate("94402", overrides={"rent": 1})
    with pytest.raises(EstimateDataError, match="finite"):
        estimate("94402", overrides={"rent_psf_month": True})
    with pytest.raises(EstimateDataError, match=">= 0"):
        estimate("94402", overrides={"rent_psf_month": -1})
