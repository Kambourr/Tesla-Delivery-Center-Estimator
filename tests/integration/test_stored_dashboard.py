"""Stored rows keep every number the dashboard and the map paint."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

from dce.app.results import COMPUTED_AT, build_ui_result
from dce.precompute import get_zip_result, precompute
from dce.precompute.payload import canonical_estimate_json

# SHA-256 of canonical_estimate_json before the stored document was compacted.
# The isolated-origin rung must not move these three ZIPs.
_ESTIMATE_SHA256 = {
    "94402": "9b738236ec99229bf5adf836a7593a860ec63d81bfebd2285d59c804b54fba63",
    "78701": "14c0b2863c1671808a8d118b60f3db110ddad430f05c777b357922b0309c2196",
    "10001": "e5c3aaf99aacecd3a262c4e264fd2fe6007aca6f72ba37dedd813f8650812a9b",
}


def test_served_zip_estimates_are_unchanged() -> None:
    for code, digest in _ESTIMATE_SHA256.items():
        raw = canonical_estimate_json(code).encode("utf-8")
        assert hashlib.sha256(raw).hexdigest() == digest


def test_stored_dashboard_matches_the_full_document(tmp_path: Path) -> None:
    codes = ("94402", "78701", "10001")
    precompute(data_dir=tmp_path, zip_codes=codes, workers=1)
    for code in codes:
        full = build_ui_result(code, source="precomputed", computed_at=COMPUTED_AT)
        stored = get_zip_result(code, data_dir=tmp_path)
        assert stored is not None
        assert _dashboard_text(full) == _dashboard_text(stored)
        assert _displayed_numbers(full) == _displayed_numbers(stored)


def _dashboard_text(result: dict[str, object]) -> str:
    """The strings ``renderDashboard`` and the catchment paint read."""
    lines = [str(item) for item in _displayed_numbers(result)]
    return "\n".join(lines)


def _displayed_numbers(result: dict[str, object]) -> list[object]:
    geo = _mapping(result["geo"])
    out: list[object] = [
        geo["county_fips"],
        geo["state"],
        result["zip_code"],
        _money(result["cost_per_delivery"]),
        _count(result["estimated_annual_deliveries"]),
        result["cost_per_delivery"],
        result["estimated_annual_deliveries"],
    ]
    drivers = result["drivers"]
    assert isinstance(drivers, list)
    for driver in drivers[:3]:
        assert isinstance(driver, dict)
        out.append(driver.get("label") or driver.get("name"))
        out.append(_money(driver["usd"]))
        out.append(_js_round(_number(driver["share"]) * 100))
        out.append(driver["usd"])
        out.append(driver["share"])
    dcf = _mapping(result["dcf"])
    for name in ("standalone", "incremental"):
        lens = _mapping(dcf[name])
        out.extend(
            [
                _money(lens["npv"]),
                _pct(lens["irr"]),
                _years(lens["simple_payback_years"]),
                _years(lens["discounted_payback_years"]),
                lens["npv"],
                lens["irr"],
                lens["simple_payback_years"],
                lens["discounted_payback_years"],
            ]
        )
        for row in _rows(lens["years"]):
            out.extend(
                [
                    row["year"],
                    _count(row["deliveries"]),
                    _money(row["benefit"]),
                    _money(row["opex"]),
                    _money(row["fcf"]),
                    _money(row["cumulative_fcf"]),
                    row["deliveries"],
                    row["benefit"],
                    row["opex"],
                    row["fcf"],
                    row["cumulative_fcf"],
                ]
            )
    scenarios = _mapping(result["scenarios"])
    for key in ("low", "base", "high"):
        card = _mapping(scenarios[key])
        standalone = _mapping(card["standalone"])
        out.extend(
            [
                _money(standalone["npv"]),
                _money(card["cost_per_delivery"]),
                _pct(standalone["irr"]),
                standalone["npv"],
                card["cost_per_delivery"],
                standalone["irr"],
            ]
        )
    for bar in _rows(result["tornado"]):
        out.extend(
            [
                bar.get("label") or bar.get("driver"),
                bar["npv_low"],
                bar["npv_base"],
                bar["npv_high"],
            ]
        )
    for center in _rows(result["nearby_centers"]):
        taken = center["deliveries_taken"]
        out.extend(
            [
                center["name"],
                center["city"],
                f"{_number(center['distance_miles']):.1f}",
                "" if taken is None else _count(taken),
                center["distance_miles"],
                taken,
            ]
        )
    catchment = _mapping(result["catchment"])
    gravity = _mapping(catchment["gravity"])
    for row in _rows(gravity["zips"]):
        out.extend([row["zip_code"], row["share"]])
    return out


def _rows(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    return [row for row in value if isinstance(row, dict)]


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _number(value: object) -> float:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value)


def _js_round(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _money(value: object) -> str:
    if value is None:
        return "—"
    number = _number(value)
    if math.isnan(number):
        return "—"
    sign = "−" if number < 0 else ""
    absolute = abs(number)
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    return f"{sign}${_js_round(absolute):,}"


def _count(value: object) -> str:
    if value is None:
        return "—"
    return f"{_js_round(_number(value)):,}"


def _pct(value: object) -> str:
    if value is None:
        return "—"
    return f"{_number(value) * 100:.1f}%"


def _years(value: object) -> str:
    if value is None:
        return "Never"
    return f"{_number(value):.2f} yr"
