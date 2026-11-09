"""The app workflow builds an artifact and does not publish a release."""

from __future__ import annotations

import importlib.util
import json
import platform
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_app_bundle_runs_the_full_precompute() -> None:
    script = (ROOT / "scripts" / "build_macos.sh").read_text(encoding="utf-8")
    commands = [
        line
        for line in script.splitlines()
        if "dce precompute" in line and not line.strip().startswith("#")
    ]
    assert len(commands) == 1
    assert "--data-dir" in commands[0]
    assert "--sample" not in commands[0]
    assert "--limit" not in commands[0]
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "app-bundle:" in makefile
    assert "--app-bundle" in makefile


def test_build_script_refuses_to_start_off_apple_silicon() -> None:
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        pytest.skip("This machine would start a real build.")
    proc = subprocess.run(
        ["./scripts/build_macos.sh", "--app-bundle"],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert proc.returncode == 1
    assert "macOS" in proc.stderr or "arm64" in proc.stderr


def test_macos_workflow_uploads_an_artifact_and_does_not_publish() -> None:
    text = (ROOT / ".github" / "workflows" / "macos-app.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "tags:" in text
    assert "macos-latest" in text
    assert "make app-bundle" in text
    assert "actions/upload-artifact@v4" in text
    assert "DCE_REQUIRE_FROZEN" in text
    for banned in (
        "softprops/action-gh-release",
        "gh release",
        "action-gh-release",
        "--sample",
        "--limit",
    ):
        assert banned not in text
    existing = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "app-bundle" not in existing
    assert "PyInstaller" not in existing


def test_offline_basemap_has_no_remote_urls() -> None:
    style = json.loads(
        (ROOT / "src" / "dce" / "app" / "web" / "vendor" / "basemap-offline.json").read_text(
            encoding="utf-8"
        )
    )
    assert style["sources"] == {}
    assert "glyphs" not in style
    assert "sprite" not in style
    blob = json.dumps(style)
    assert "http://" not in blob
    assert "https://" not in blob
    page = (ROOT / "src" / "dce" / "app" / "web" / "app.js").read_text(encoding="utf-8")
    assert "vendor/basemap-offline.json" in page


def test_print_app_report_writes_the_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = {
        "app_bytes": 10,
        "results_db_bytes": 4,
        "precompute_seconds": 1.5,
        "rows": {"ok": 2, "error": 1},
        "cold_start_ms": 20,
        "click_ms": {"94402": 1, "78701": 2},
        "opened_from": "meipass",
    }
    monkeypatch.chdir(tmp_path)
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "app-report.json").write_text(json.dumps(report), encoding="utf-8")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    spec = importlib.util.spec_from_file_location(
        "print_app_report", ROOT / "scripts" / "print_app_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main() == 0
    text = summary.read_text(encoding="utf-8")
    assert "10 bytes" in text
    assert "1.5 seconds" in text
    assert "94402" in text
