"""Packaged results database: read-only bundle, or one copy on first launch."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import dce.config as config
from dce.app.runtime import bundled_results_db, packaged_support_dir, prepare_packaged_results
from dce.app.smoke import run_smoke
from dce.precompute import get_zip_result, result_counts
from dce.storage.connection import get_connection
from dce.storage.repository import ZipResultRecord, upsert_zip_results


@pytest.fixture
def clean_results_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DCE_RESULTS_DIR", raising=False)
    monkeypatch.delenv("DCE_RESULTS_READONLY", raising=False)
    monkeypatch.delenv("DCE_RESULTS_PREPARED", raising=False)
    monkeypatch.delenv("DCE_RESULTS_OPENED_FROM", raising=False)
    monkeypatch.delenv("DCE_SMOKE_OUT", raising=False)


def _database(directory: Path) -> Path:
    conn = get_connection(directory)
    rows = [
        ZipResultRecord(
            zip_code=zip_code,
            model_version="test",
            inputs_hash="abc",
            status="ok",
            reason=None,
            payload_json=json.dumps({"schema": "dce.ui_result.v1", "zip_code": zip_code}),
            computed_at="2026-11-09T00:00:00+00:00",
            elapsed_ms=1.0,
        )
        for zip_code in ("94402", "78701")
    ]
    upsert_zip_results(conn, rows)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    conn.close()
    return directory / "dce.sqlite"


def _install_bundle(monkeypatch: pytest.MonkeyPatch, root: Path, database: Path) -> None:
    seed = root / "data" / "seed"
    seed.mkdir(parents=True)
    results = root / "data" / "results"
    results.mkdir(parents=True)
    target = results / "dce.sqlite"
    target.write_bytes(database.read_bytes())
    monkeypatch.setattr(config.sys, "_MEIPASS", str(root), raising=False)


def test_checkout_keeps_the_adr_0002_directory(
    clean_results_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path / "absent"), raising=False)
    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    directory, opened = prepare_packaged_results()
    assert opened == "user"
    assert directory == tmp_path / ".local" / "share" / "delivery-center-estimator"
    assert "DCE_RESULTS_READONLY" not in os.environ
    assert bundled_results_db() is None


def test_support_dir_on_windows_uses_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("dce.app.runtime.sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert packaged_support_dir() == tmp_path / "Local" / "DCE"


def test_frozen_app_reads_the_bundled_database_without_copying(
    clean_results_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _database(tmp_path / "built")
    root = tmp_path / "meipass"
    _install_bundle(monkeypatch, root, source)
    monkeypatch.setattr("dce.app.runtime.sys.platform", "darwin")
    monkeypatch.setattr("dce.app.runtime.Path.home", staticmethod(lambda: tmp_path / "home"))
    directory, opened = prepare_packaged_results()
    assert opened == "meipass"
    assert directory == root / "data" / "results"
    assert bundled_results_db() == directory / "dce.sqlite"
    assert not (tmp_path / "home").exists()
    found = get_zip_result("94402")
    assert found is not None
    assert found["zip_code"] == "94402"
    assert result_counts() == {"ok": 2, "error": 0}
    assert not (directory / "dce.sqlite-wal").exists()
    again, opened_again = prepare_packaged_results()
    assert again == directory
    assert opened_again == "meipass"


def test_first_launch_copies_when_the_bundle_cannot_be_opened(
    clean_results_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = _database(tmp_path / "built")
    root = tmp_path / "meipass"
    _install_bundle(monkeypatch, root, source)
    home = tmp_path / "home"
    monkeypatch.setattr("dce.app.runtime.sys.platform", "darwin")
    monkeypatch.setattr("dce.app.runtime.Path.home", staticmethod(lambda: home))

    def _openable(path: Path) -> bool:
        return "Application Support" in path.as_posix()

    monkeypatch.setattr("dce.app.runtime.can_open_readonly", _openable)
    directory, opened = prepare_packaged_results()
    dest = home / "Library" / "Application Support" / "DCE" / "dce.sqlite"
    assert opened == "application_support"
    assert directory == dest.parent
    assert packaged_support_dir() == dest.parent
    assert dest.is_file()
    assert dest.stat().st_size == source.stat().st_size
    assert get_zip_result("78701") is not None


def test_smoke_reads_both_zips_from_the_bundled_database(
    clean_results_env: None,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _database(tmp_path / "built")
    root = tmp_path / "meipass"
    _install_bundle(monkeypatch, root, source)
    out = tmp_path / "smoke.json"
    monkeypatch.setenv("DCE_SMOKE_OUT", str(out))
    assert run_smoke(0.0) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["ok"] is True
    assert report["opened_from"] == "meipass"
    assert report["rows"] == {"ok": 2, "error": 0}
    clicks = {row["zip"]: row for row in report["clicks"]}
    assert set(clicks) == {"94402", "78701"}
    for zip_code, row in clicks.items():
        assert row["source"] == "precomputed"
        assert row["click_ms"] >= 0
        assert row["result"]["zip_code"] == zip_code
    printed = json.loads(capsys.readouterr().out)
    assert printed["ok"] is True
