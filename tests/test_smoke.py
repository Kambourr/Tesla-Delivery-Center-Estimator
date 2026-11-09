"""M0 smoke test: the package imports and the stub CLI help exits 0."""

from __future__ import annotations

import pytest

from dce import __version__
from dce.cli import main


def test_cli_help_smoke(capsys: pytest.CaptureFixture[str]) -> None:
    assert __version__ == "0.0.0"
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out
    assert "public data only" in out
