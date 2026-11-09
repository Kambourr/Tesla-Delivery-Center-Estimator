"""OS application-data paths from ADR-0002."""

from __future__ import annotations

from pathlib import Path

import pytest

import dce.config as config


def test_macos_user_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config.sys, "platform", "darwin")
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    path = config.user_data_dir()
    assert path == tmp_path / "Library" / "Application Support" / "DeliveryCenterEstimator"
    assert config.user_db_path() == path / "dce.sqlite"
    assert not path.exists()


def test_windows_user_data_dir_uses_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    assert config.user_data_dir() == tmp_path / "LocalAppData" / "DeliveryCenterEstimator"
    assert config.user_db_path().name == "dce.sqlite"


def test_windows_user_data_dir_falls_back_without_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    assert config.user_data_dir() == tmp_path / "AppData" / "Local" / "DeliveryCenterEstimator"


def test_linux_user_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    path = config.user_data_dir()
    assert path == tmp_path / ".local" / "share" / "delivery-center-estimator"
    assert not path.exists()


def test_bundled_paths_stay_inside_the_repository() -> None:
    seed = config.bundled_seed_dir()
    assumptions = config.assumptions_path()
    assert seed.is_dir()
    assert (seed / "README.md").is_file()
    assert assumptions == seed.parent / "defaults" / "assumptions.yaml"
    assert assumptions.name == "assumptions.yaml"


def test_frozen_bundle_root_is_meipass(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seed = tmp_path / "data" / "seed"
    seed.mkdir(parents=True)
    defaults = tmp_path / "data" / "defaults"
    defaults.mkdir()
    (defaults / "assumptions.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config.bundle_root() == tmp_path
    assert config.bundled_seed_dir() == seed
    assert config.assumptions_path() == defaults / "assumptions.yaml"
    assert config.demo_data_dir() == tmp_path / "data" / "demo"


def test_meipass_without_a_seed_directory_is_not_the_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert config.bundle_root() is None
    assert config.bundled_seed_dir().is_dir()
