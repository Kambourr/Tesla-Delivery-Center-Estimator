"""Local .env loading never overrides the environment and never logs the value."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import dce.config as config


def test_env_file_fills_a_missing_key_and_does_not_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "_project_root", lambda: tmp_path)
    monkeypatch.delenv("CENSUS_API_KEY", raising=False)
    monkeypatch.delenv("BLS_API_KEY", raising=False)
    (tmp_path / ".env").write_text(
        '\n# comment\nexport CENSUS_API_KEY="from-file"\nBLS_API_KEY=from-file-bls\n',
        encoding="utf-8",
    )
    assert config.api_key("CENSUS_API_KEY") == "from-file"
    monkeypatch.setenv("CENSUS_API_KEY", "from-env")
    assert config.api_key("CENSUS_API_KEY") == "from-env"
    assert os.environ["BLS_API_KEY"] == "from-file-bls"


def test_demo_dir_is_inside_the_repository() -> None:
    demo = config.demo_data_dir()
    assert demo.is_dir()
    assert (demo / "san_mateo" / "census_acs_2024.json").is_file()


def test_bad_key_name_raises() -> None:
    with pytest.raises(config.ConfigError, match="identifier"):
        config.api_key("not a key")
