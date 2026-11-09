"""End-to-end San Mateo estimate. Fixtures only: no network."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from dce.config import assumptions_path
from dce.model.assumptions import parse_assumptions
from dce.model.costs import build_cost_inputs
from dce.model.dcf import build_dcf_inputs, run_dcf_views
from dce.model.types import Scenario
from dce.orchestrator import EstimateDataError, estimate

# Research illustrative case (dcf_design.md §4) uses 4,400 steady deliveries,
# the old nearest-center figure rounded. This pipeline feeds gravity after
# the county Tesla anchor, the base handover factor 1.10, and the US
# delivery list. The building stays 25,000 SF.
RESEARCH_STEADY = 4_400.0
RENT = 2.14
ENERGY = 0.2875
DEMAND_RATE = 20.50


def _research_views(
    steady: float,
    *,
    rent: float = RENT,
    wage_annual: float | None = None,
    opex_load: float | None = None,
    fitout_index: float = 1.0,
) -> tuple[float, float | None, float | None, float | None, float]:
    raw = yaml.safe_load(assumptions_path().read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assumptions = parse_assumptions(raw)
    scenario = Scenario(vehicle_mix=dict(assumptions.vehicle_mix), wage_shock=0.0)
    wage = (
        assumptions.labor.fallback_wage_hourly * assumptions.labor.paid_hours_per_fte
        if wage_annual is None
        else wage_annual
    )
    costs = build_cost_inputs(
        assumptions,
        rent_psf_month=rent,
        wage_annual=wage,
        energy_rate_kwh=ENERGY,
        demand_rate_kw=DEMAND_RATE,
        annual_deliveries=steady,
        opex_load=opex_load,
        fitout_index=fitout_index,
    )
    dcf = replace(
        build_dcf_inputs(assumptions),
        fitout_psf=assumptions.capex.fitout_psf * fitout_index,
    )
    views = run_dcf_views(costs, assumptions, steady_deliveries=steady, scenario=scenario, dcf=dcf)
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
    −$2.8M. This run feeds gravity after the county anchor and handover
    factor 1.10 on the US delivery list (about 5,808). That raises
    standalone NPV and IRR and shortens payback versus 4,400. Incremental
    stays near −$2.8M because that lens scales cost and benefit together.
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
    assert gravity == pytest.approx(5565.2, abs=1)
    assert nearest == pytest.approx(4468.8, abs=1)
    assert nearest < gravity
    assert result.estimated_annual_deliveries == pytest.approx(gravity)
    assert [row.center_id for row in result.catchment.gravity.taken_from[:2]] == [
        "colma",
        "sunnyvale",
    ]
    assert result.catchment.nearest.zips
    # The 2026 nationwide surface puts one more ZIP in the nearest-center case.
    assert len(result.catchment.nearest.zips) == 21
    taken = sum(row.deliveries_per_year for row in result.catchment.gravity.taken_from)
    assert taken == pytest.approx(gravity, abs=1)

    assert [driver.name for driver in result.drivers] == ["labor", "lease", "capex"]
    assert result.dcf.standalone.discount_rate == pytest.approx(0.136)
    assert result.map_path is None

    anchor_npv, anchor_irr, anchor_payback, _anchor_disc, anchor_incremental = _research_views(
        RESEARCH_STEADY
    )
    assert anchor_npv == pytest.approx(9.7e6, abs=0.1e6)
    assert anchor_irr == pytest.approx(0.66, abs=0.01)
    assert anchor_payback == pytest.approx(1.7, abs=0.05)
    assert anchor_incremental == pytest.approx(-2.8e6, abs=0.25e6)

    by_name = {row.name: row for row in result.provenance}
    rent_row = by_name["rent_psf_month"]
    rent = rent_row.value
    wage = by_name["wage_annual"].value
    energy = by_name["energy_rate_kwh"]
    tax = by_name["property_tax_rate"]
    assert rent == pytest.approx(2.14)
    assert rent_row.source == "cbsa_raw"
    assert rent_row.geography_level == "cbsa"
    assert rent_row.geography_id == "41884"
    assert rent_row.fallback is False
    assert "Kidder" in rent_row.detail
    assert wage == pytest.approx(75730)
    assert energy.source == "pge_pdf"
    assert energy.fallback is False
    assert energy.value == pytest.approx(0.2875)
    assert tax.fallback is True
    assert "Los Angeles" in tax.detail
    assert "not a studied county" in tax.detail
    assert rent is not None and wage is not None
    opex = by_name["opex_load"].value
    fitout = by_name["fitout_index"].value
    assert opex is not None and fitout is not None
    adjusted_npv, adjusted_irr, adjusted_payback, adjusted_disc, adjusted_incremental = (
        _research_views(gravity, rent=rent, wage_annual=wage, opex_load=opex, fitout_index=fitout)
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

    # Local OEWS wage and the 2026 CEC annualization move both lenses off the
    # old fallback-wage / 2025-extract case. Rent is the observed Kidder
    # headline, $2.14. The 4,400-delivery reconstruction above is the
    # published-model lock.
    assert len(standalone.years) == 11
    assert standalone.years[0].capex == pytest.approx(
        100.0 * fitout * 25_000.0 * 1.20 + 780_000.0, abs=1
    )


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
