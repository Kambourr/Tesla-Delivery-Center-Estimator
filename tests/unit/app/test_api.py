"""Python bridge: cache, precomputed results, worker thread, and 94402."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from dce.app.api import AppApi
from dce.app.results import UI_RESULT_SCHEMA, build_ui_result, compare_metrics, ui_result_problems
from dce.orchestrator import estimate

ROOT = Path(__file__).resolve().parents[3]


def _minimal(zip_code: str, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": UI_RESULT_SCHEMA,
        "zip_code": zip_code,
        "source": "computed",
        "cost_per_delivery": 10.0,
    }
    payload.update(extra)
    return payload


def _api(**kwargs: object) -> AppApi:
    return AppApi(**kwargs)  # type: ignore[arg-type]


def test_bootstrap_loads_bay_area_fixture_and_centers() -> None:
    api = _api()
    try:
        body = api.bootstrap()
    finally:
        api.close()
    assert body["ok"] is True
    zcta = body["zcta"]
    assert isinstance(zcta, dict)
    features = zcta["features"]
    assert isinstance(features, list)
    zips = {feature["properties"]["zip"] for feature in features if isinstance(feature, dict)}
    assert "94402" in zips
    centers = body["centers"]
    assert isinstance(centers, list)
    assert "colma" in {row["center_id"] for row in centers if isinstance(row, dict)}
    assert str(body["basemap_style"]).startswith("vendor/")
    assert body["basemap_fallback"] == "vendor/basemap-offline.json"
    boundaries = body["boundaries"]
    assert isinstance(boundaries, dict)
    assert boundaries["mode"] in {"geojson", "pmtiles"}
    assert boundaries["source_layer"] == "zcta"


def test_94402_matches_estimate_and_carries_the_dashboard_fields() -> None:
    result = build_ui_result("94402")
    assert ui_result_problems(result) == []
    baseline = estimate("94402")
    assert result["cost_per_delivery"] == pytest.approx(baseline.cost_per_delivery)
    assert result["estimated_annual_deliveries"] == pytest.approx(
        baseline.estimated_annual_deliveries
    )
    assert result["drivers"][0]["name"] == "labor"  # type: ignore[index]
    assert [row["name"] for row in result["drivers"]] == ["labor", "lease", "capex"]  # type: ignore[index, union-attr]
    standalone = result["dcf"]["standalone"]  # type: ignore[index]
    assert baseline.dcf is not None
    assert standalone["npv"] == pytest.approx(baseline.dcf.standalone.npv)
    assert result["tornado"][0]["driver"] == "deliveries"  # type: ignore[index]
    base = result["scenarios"]["base"]  # type: ignore[index]
    assert base["standalone"]["npv"] == pytest.approx(standalone["npv"], abs=1.0)  # type: ignore[index]
    assert result["catchment"]["gravity"]["zips"]  # type: ignore[index]
    assert result["nearby_centers"]  # type: ignore[index]


def test_78701_scenario_base_matches_estimate() -> None:
    result = build_ui_result("78701")
    baseline = estimate("78701")
    assert baseline.dcf is not None
    base = result["scenarios"]["base"]  # type: ignore[index]
    assert base["standalone"]["npv"] == pytest.approx(baseline.dcf.standalone.npv, abs=1.0)  # type: ignore[index]
    assert result["cost_per_delivery"] == pytest.approx(baseline.cost_per_delivery)  # type: ignore[index]
    energy = {row.name: row for row in baseline.provenance}["energy_rate_kwh"]
    assert energy.source == "eia861"
    assert energy.geography_id == "1015"
    assert energy.fallback is False
    tornado = result["tornado"][0]  # type: ignore[index]
    assert tornado["npv_base"] == pytest.approx(baseline.dcf.standalone.npv, abs=1.0)  # type: ignore[index]


def test_get_result_caches_and_runs_on_a_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake(zip_code: str) -> dict[str, object]:
        seen.append(threading.current_thread().name)
        time.sleep(0.05)
        return _minimal(zip_code)

    monkeypatch.setattr("dce.app.api.build_ui_result", fake)
    api = _api()
    try:
        first = api.get_result("94402")
        second = api.get_result("94402")
    finally:
        api.close()
    assert first["source"] == "computed"
    assert second["source"] == "cache"
    assert seen == ["dce-ui_0"] or seen[0].startswith("dce-ui")
    assert len(seen) == 1
    assert threading.current_thread().name != seen[0]


def test_concurrent_calls_compute_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake(zip_code: str) -> dict[str, object]:
        calls.append(1)
        time.sleep(0.2)
        return _minimal(zip_code)

    monkeypatch.setattr("dce.app.api.build_ui_result", fake)
    api = _api()
    results: list[dict[str, object]] = []

    def run() -> None:
        results.append(api.get_result("94402"))

    try:
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        api.close()
    assert calls == [1]
    assert len(results) == 2
    assert all(row.get("ok") is True for row in results)


def test_precomputed_file_and_directory_skip_compute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "dce.app.api.build_ui_result",
        lambda _zip: (_ for _ in ()).throw(AssertionError("computed")),
    )
    single = tmp_path / "one.json"
    single.write_text(json.dumps({"94401": _minimal("94401")}), encoding="utf-8")
    api = _api(results_path=single)
    try:
        assert api.get_result("94401")["source"] == "precomputed"
    finally:
        api.close()

    folder = tmp_path / "rows"
    folder.mkdir()
    (folder / "94403.json").write_text(json.dumps(_minimal("94403")), encoding="utf-8")
    api = _api(results_path=folder)
    try:
        body = api.get_result("94403")
    finally:
        api.close()
    assert body["source"] == "precomputed"
    assert body["result"]["zip_code"] == "94403"  # type: ignore[index]


def test_bad_precomputed_falls_through(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dce.app.api.build_ui_result", lambda zip_code: _minimal(zip_code, source="computed")
    )
    path = tmp_path / "results.json"
    path.write_text("{", encoding="utf-8")
    api = _api(results_path=path)
    try:
        body = api.get_result("94402")
    finally:
        api.close()
    assert body["source"] == "computed"


def test_repository_hook_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dce.storage.repository.get_zip_result",
        lambda zip_code: _minimal(zip_code),
        raising=False,
    )
    monkeypatch.setattr(
        "dce.app.api.build_ui_result",
        lambda _zip: (_ for _ in ()).throw(AssertionError("computed")),
    )
    api = _api(use_repository=True)
    try:
        assert api.get_result("94404")["source"] == "precomputed"
    finally:
        api.close()


def test_invalid_and_unknown_zips_do_not_raise() -> None:
    api = _api()
    try:
        invalid = api.get_result("12")
        unknown = api.get_result("00000")
    finally:
        api.close()
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "invalid_zip"  # type: ignore[index]
    assert unknown["ok"] is False
    assert unknown["error"]["code"] == "unknown_zip"  # type: ignore[index]


def test_compare_highlights_the_better_value(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(zip_code: str) -> dict[str, object]:
        cost = 400.0 if zip_code == "94402" else 700.0
        npv = 2_000_000.0 if zip_code == "94402" else -1_000_000.0
        return {
            "schema": UI_RESULT_SCHEMA,
            "zip_code": zip_code,
            "cost_per_delivery": cost,
            "estimated_annual_deliveries": 5000.0 if zip_code == "94402" else 3000.0,
            "dcf": {
                "standalone": {
                    "npv": npv,
                    "irr": 0.4 if zip_code == "94402" else None,
                    "simple_payback_years": 1.2 if zip_code == "94402" else None,
                    "discounted_payback_years": 1.5 if zip_code == "94402" else 4.0,
                },
                "incremental": {
                    "npv": npv / 2,
                    "irr": None,
                    "simple_payback_years": None,
                    "discounted_payback_years": None,
                },
            },
        }

    monkeypatch.setattr("dce.app.api.build_ui_result", fake)
    api = _api()
    try:
        body = api.compare("94402", "94404")
    finally:
        api.close()
    assert body["ok"] is True
    metrics = {row["id"]: row for row in body["metrics"]}  # type: ignore[union-attr]
    assert metrics["cost_per_delivery"]["winner"] == "a"
    assert metrics["standalone_npv"]["winner"] == "a"
    assert metrics["standalone_irr"]["winner"] == "a"
    assert metrics["standalone_simple_payback_years"]["winner"] == "a"
    assert metrics["incremental_irr"]["winner"] == "tie"
    api2 = _api()
    try:
        same = api2.compare("94402", "94402")
    finally:
        api2.close()
    assert same["ok"] is False


def test_compare_metrics_payback_none_loses() -> None:
    left = {
        "cost_per_delivery": 1,
        "estimated_annual_deliveries": 1,
        "dcf": {"standalone": {"simple_payback_years": None}, "incremental": {}},
    }
    right = {
        "cost_per_delivery": 1,
        "estimated_annual_deliveries": 1,
        "dcf": {"standalone": {"simple_payback_years": 3.0}, "incremental": {}},
    }
    rows = {row["id"]: row for row in compare_metrics(left, right)}
    assert rows["standalone_simple_payback_years"]["winner"] == "b"
    assert rows["cost_per_delivery"]["winner"] == "tie"


def test_disk_cache_survives_a_new_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake(zip_code: str) -> dict[str, object]:
        calls["n"] += 1
        return _minimal(zip_code)

    monkeypatch.setattr("dce.app.api.build_ui_result", fake)
    api = _api(cache_dir=tmp_path, persist_cache=True)
    try:
        assert api.get_result("94402")["source"] == "computed"
    finally:
        api.close()
    monkeypatch.setattr(
        "dce.app.api.build_ui_result",
        lambda _zip: (_ for _ in ()).throw(AssertionError("recomputed")),
    )
    again = _api(cache_dir=tmp_path, persist_cache=True)
    try:
        assert again.get_result("94402")["source"] == "cache"
    finally:
        again.close()
    assert calls["n"] == 1


def test_pmtiles_archive_switches_the_map_to_nationwide_tiles(tmp_path: Path) -> None:
    archive = tmp_path / "zcta_us.pmtiles"
    archive.write_bytes(b"not a real archive")
    api = _api(pmtiles_path=archive)
    try:
        body = api.bootstrap()
    finally:
        api.close()
    assert body["ok"] is True
    boundaries = body["boundaries"]
    assert isinstance(boundaries, dict)
    assert boundaries["mode"] == "pmtiles"
    assert boundaries["pmtiles"] == "tiles/zcta_us.pmtiles"
    assert boundaries["minzoom"] == 3
    assert boundaries["maxzoom"] == 8
    index = body["zip_index"]
    assert isinstance(index, list)
    assert any(row.get("zip") == "94402" for row in index if isinstance(row, dict))
    assert any(row.get("zip") == "00601" for row in index if isinstance(row, dict))


def test_precompute_adapter_prefers_get_zip_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "dce.storage.repository.get_zip_result",
        lambda zip_code: _minimal(zip_code),
        raising=False,
    )
    monkeypatch.setattr(
        "dce.app.api.build_ui_result",
        lambda _zip: (_ for _ in ()).throw(AssertionError("computed")),
    )
    api = _api(use_repository=True, pmtiles_path=None)
    try:
        body = api.get_result("94401")
    finally:
        api.close()
    assert body["source"] == "precomputed"
    assert body["result"]["zip_code"] == "94401"  # type: ignore[index]


def test_missing_zcta_file_is_an_error(tmp_path: Path) -> None:
    api = _api(zcta_path=tmp_path / "missing.geojson")
    try:
        body = api.bootstrap()
    finally:
        api.close()
    assert body["ok"] is False
    assert body["error"]["code"] == "map_failed"  # type: ignore[index]


def test_build_script_refuses_to_cross_compile() -> None:
    script = (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")
    assert "Darwin" in script
    assert "arm64" in script
    assert "PyInstaller" in script
    spec = (ROOT / "packaging" / "dce_macos.spec").read_text(encoding="utf-8")
    assert "dce/app/web" in spec
    assert "data/seed" in spec
    assert "data/geo" in spec
