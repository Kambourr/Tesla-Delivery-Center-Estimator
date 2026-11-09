"""Stored ZIP results: a few ZIPs, a resume, and the read API."""

from __future__ import annotations

from pathlib import Path

import pytest

from dce.app.precomputed import lookup_zip_result
from dce.app.results import UI_RESULT_SCHEMA, ui_result_problems
from dce.precompute import get_zip_result, get_zip_results, precompute
from dce.precompute.version import MODEL_VERSION, inputs_hash
from dce.storage.connection import get_connection
from dce.storage.repository import ZipResultRecord, upsert_zip_results


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("precompute")


def test_precompute_stores_ok_and_error_rows_and_resumes(data_dir: Path) -> None:
    first = precompute(
        data_dir=data_dir,
        zip_codes=("94402", "78701", "01301", "01003", "96799"),
        workers=1,
    )
    assert first.computed == 5
    assert first.errors == 0
    assert first.skipped == 0
    assert first.model_version == MODEL_VERSION
    assert first.db_bytes > 0
    conn = get_connection(data_dir)
    try:
        stored = conn.execute(
            "SELECT typeof(payload_json) FROM zip_result WHERE zip = '78701'"
        ).fetchone()
        assert stored is not None
        assert stored[0] == "blob"
        assert conn.execute("PRAGMA page_size").fetchone()[0] == 512
    finally:
        conn.close()

    austin = get_zip_result("78701", data_dir=data_dir)
    assert austin is not None
    assert austin["schema"] == UI_RESULT_SCHEMA
    assert austin["zip_code"] == "78701"
    assert austin["source"] == "precomputed"
    assert austin["current"] is True
    assert austin["inputs_hash"] == inputs_hash()
    assert austin["model_version"] == MODEL_VERSION
    assert ui_result_problems(austin) == []
    scenarios = austin["scenarios"]
    assert isinstance(scenarios, dict)
    base = scenarios["base"]
    assert isinstance(base, dict)
    assert base["cost_per_delivery"] > 0
    standalone = austin["dcf"]["standalone"]  # type: ignore[index]
    assert isinstance(standalone, dict)
    assert len(standalone["years"]) == 11
    assert "npv" in base["standalone"]  # type: ignore[index]
    assert "years" not in base["standalone"]  # type: ignore[operator]
    assert austin["tornado"]
    catchment = austin["catchment"]
    assert isinstance(catchment, dict)
    gravity = catchment["gravity"]
    assert isinstance(gravity, dict)
    assert gravity["zips"]
    assert austin["nearby_centers"]
    assert "provenance" not in austin
    gravity_zips = gravity["zips"]
    assert isinstance(gravity_zips, list) and gravity_zips
    assert "share" in gravity_zips[0]
    assert "deliveries_per_year" not in gravity_zips[0]
    year0 = standalone["years"][0]
    assert isinstance(year0, dict)
    assert set(year0) == {"year", "deliveries", "benefit", "opex", "fcf", "cumulative_fcf"}

    samoa = get_zip_result("96799", data_dir=data_dir)
    assert samoa is not None
    assert samoa["schema"] == UI_RESULT_SCHEMA
    assert samoa["zip_code"] == "96799"
    assert float(samoa["estimated_annual_deliveries"]) > 0

    many = get_zip_results(("78701", "99999", "94402"), data_dir=data_dir)
    assert list(many) == ["78701", "94402"]
    assert get_zip_result("99999", data_dir=data_dir) is None

    second = precompute(
        data_dir=data_dir,
        zip_codes=("94402", "78701", "01301", "01003", "96799"),
        workers=1,
    )
    assert second.computed == 0
    assert second.skipped == 5

    conn = get_connection(data_dir)
    try:
        upsert_zip_results(
            conn,
            [
                ZipResultRecord(
                    zip_code="94402",
                    model_version=MODEL_VERSION,
                    inputs_hash=inputs_hash(),
                    status="error",
                    reason="forced for resume",
                    payload_json='{"zip_code":"94402","status":"error","reason":"forced for resume"}',
                    computed_at="2026-11-09T00:00:00+00:00",
                    elapsed_ms=1.0,
                )
            ],
        )
    finally:
        conn.close()
    retried = precompute(
        data_dir=data_dir,
        zip_codes=("94402",),
        workers=1,
        retry_errors=True,
    )
    assert retried.computed == 1
    assert retried.errors == 0
    restored = get_zip_result("94402", data_dir=data_dir)
    assert restored is not None
    assert restored["schema"] == UI_RESULT_SCHEMA


def test_lookup_zip_result_returns_the_stored_94402_document(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dce.precompute.run.user_data_dir", lambda: data_dir)
    precompute(data_dir=data_dir, zip_codes=("94402",), workers=1)
    found = lookup_zip_result("94402")
    assert isinstance(found, dict)
    assert found["schema"] == UI_RESULT_SCHEMA
    assert found["zip_code"] == "94402"
    assert found["source"] == "precomputed"
    assert ui_result_problems(found) == []
    assert found["model_version"] == MODEL_VERSION
    assert found["inputs_hash"] == inputs_hash()


def test_precompute_workers_write_rows(data_dir: Path) -> None:
    report = precompute(
        data_dir=data_dir,
        zip_codes=("94110", "78702"),
        workers=2,
    )
    assert report.computed == 2
    stored = get_zip_results(("94110", "78702"), data_dir=data_dir)
    assert set(stored) == {"94110", "78702"}
    assert stored["94110"]["schema"] == UI_RESULT_SCHEMA
    assert stored["78702"]["schema"] == UI_RESULT_SCHEMA


def test_bay_area_sample_limit_runs(data_dir: Path) -> None:
    report = precompute(data_dir=data_dir, sample="bay-area", limit=2, workers=1)
    assert report.requested == 2
    assert report.computed == 2
    assert report.errors == 0
    assert report.resolvable_zips > 30_000
