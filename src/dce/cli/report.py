"""Text and JSON renderings of an :class:`~dce.model.types.EstimateResult`.

The text form is the human summary. ``--json`` prints
:func:`result_as_dict` so a later tool can read every cash-flow row.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from dce.model.dcf import DcfResult
from dce.model.types import CatchmentCaseSummary, EstimateResult

_COUNTY_NAMES = {"06081": "San Mateo County"}


def render_text(result: EstimateResult) -> str:
    """Return a readable summary. The standalone yearly table is the headline."""
    geo = result.geo
    county = _COUNTY_NAMES.get(geo.county_fips, f"county {geo.county_fips}")
    lines = [
        f"Delivery-center estimate for {geo.zip_code} ({county}, {geo.state})",
        f"Discount rate: Tesla WACC {_percent(result.dcf.standalone.discount_rate) if result.dcf else 'n/a'}",
        "",
    ]
    if result.catchment is not None:
        gravity = result.catchment.gravity
        nearest = result.catchment.nearest
        lines.append(f"Catchment (Huff gravity, beta {result.catchment.beta:g})")
        lines.append(
            f"  Deliveries / year: {_count(gravity.deliveries_per_year)} "
            f"across {len(gravity.zips)} ZIPs"
        )
        lines.append(
            f"  Low case (nearest center): {_count(nearest.deliveries_per_year)} "
            f"across {len(nearest.zips)} ZIPs"
        )
        lines.extend(_taken_lines(gravity))
        lines.append("")
    lines.append(f"Cost per delivery: {_dollars(result.cost_per_delivery)}")
    lines.append(f"  Annualized cost: {_dollars(result.annualized_total_cost)}")
    lines.append("  Top drivers:")
    for index, driver in enumerate(result.drivers, start=1):
        lines.append(f"    {index}. {driver.name}  {_dollars(driver.usd)}  ({driver.share:.1%})")
    if result.dcf is not None:
        lines.extend(_lens_lines("DCF standalone (headline)", result.dcf.standalone))
        lines.extend(_lens_lines("DCF incremental to Tesla (check)", result.dcf.incremental))
        lines.append("")
        lines.append("Yearly cash flow, standalone")
        lines.append(
            f"  {'Year':>4}  {'Deliveries':>12}  {'Benefit':>14}  {'Opex':>14}  {'FCF':>14}"
        )
        for row in result.dcf.standalone.years:
            lines.append(
                f"  {row.year:4d}  {row.deliveries:12,.1f}  "
                f"{_dollars(row.benefit):>14}  {_dollars(row.opex):>14}  {_dollars(row.fcf):>14}"
            )
        lines.append("Incremental yearly cash flows are included in --json.")
    return "\n".join(lines)


def render_json(result: EstimateResult) -> str:
    """Return indented JSON for the full result, including both yearly tables."""
    return json.dumps(result_as_dict(result), indent=2)


def result_as_dict(result: EstimateResult) -> dict[str, object]:
    """Return a JSON-ready mapping. Tuples become lists."""
    return asdict(result)


def _lens_lines(title: str, lens: DcfResult) -> list[str]:
    irr = "n/a" if lens.irr is None else _percent(lens.irr)
    return [
        "",
        title,
        f"  NPV: {_millions(lens.npv)}",
        f"  IRR: {irr}",
        f"  Simple payback: {_years(lens.simple_payback_years)}",
        f"  Discounted payback: {_years(lens.discounted_payback_years)}",
    ]


def _taken_lines(case: CatchmentCaseSummary) -> list[str]:
    if not case.taken_from:
        return ["  Taken from existing centers: none"]
    lines = ["  Taken from existing centers:"]
    for row in case.taken_from:
        lines.append(f"    {row.name}: {_count(row.deliveries_per_year)} / year")
    return lines


def _count(value: float) -> str:
    return f"{value:,.0f}"


def _dollars(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def _millions(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value) / 1_000_000:.2f}M"


def _percent(value: float) -> str:
    return f"{value:.1%}"


def _years(value: float | None) -> str:
    if value is None:
        return "never"
    return f"{value:.2f} years"
