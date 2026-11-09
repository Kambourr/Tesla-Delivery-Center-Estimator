"""HUD ZIP crosswalk parser. The live call is not made."""

from __future__ import annotations

import pytest

from dce.data.ingest.hud_crosswalk import (
    HudTokenError,
    fetch_zip_crosswalk,
    parse_hud_results,
)


def test_parse_keeps_ratio_and_pads_a_short_geoid() -> None:
    rows = parse_hud_results(
        {
            "data": {
                "results": [
                    {"geoid": "6081", "tot_ratio": 1, "state": "CA"},
                ]
            }
        }
    )
    assert rows == ({"geoid": "06081", "tot_ratio": 1.0, "state": "CA"},)


def test_missing_token_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HUD_TOKEN", raising=False)
    monkeypatch.setattr("dce.config.load_local_env", lambda: None)

    def fail(url: str, **_kwargs: object) -> object:
        raise AssertionError(f"should not fetch {url}")

    monkeypatch.setattr("dce.data.ingest.hud_crosswalk.request_json", fail)
    with pytest.raises(HudTokenError, match="HUD_TOKEN"):
        fetch_zip_crosswalk("94402")
