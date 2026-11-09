"""Stored ZIP results: a few ZIPs, a resume, and the read API."""

from __future__ import annotations

from pathlib import Path

import pytest

from dce.app.precomputed import lookup_zip_result
from dce.app.results import UI_RESULT_SCHEMA, ui_result_problems
from dce.precompute import get_zip_result, get_zip_results, precompute
from dce.precompute.version import MODEL_VERSION, inputs_hash


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("precompute")


def test_precompute_stores_ok_and_error_rows_and_resumes(data_dir: Path) -> None:
    first = precompute(
        data_dir=data_dir,
        zip_codes=("94402", "78701", "01301", "01003", "01093"),
        workers=1,
    )
    assert first.computed == 5
    assert first.errors == 1
    assert first.skipped == 0
    assert first.model_version == MODEL_VERSION
    assert first.db_bytes > 0

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
    assert austin["provenance"]

    missing_rent = get_zip_result("01093", data_dir=data_dir)
    assert missing_rent is not None
    assert missing_rent["status"] == "error"
    reason = missing_rent["reason"]
    assert isinstance(reason, str)
    assert "01093" in reason

    many = get_zip_results(("78701", "99999", "94402"), data_dir=data_dir)
    assert list(many) == ["78701", "94402"]
    assert get_zip_result("99999", data_dir=data_dir) is None

    second = precompute(
        data_dir=data_dir,
        zip_codes=("94402", "78701", "01301", "01003", "01093"),
        workers=1,
    )
    assert second.computed == 0
    assert second.skipped == 5

    retried = precompute(
        data_dir=data_dir,
        zip_codes=("01093",),
        workers=1,
        retry_errors=True,
    )
    assert retried.computed == 1
    assert retried.errors == 1


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
