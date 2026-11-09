"""EIA table parser and OpenEI rate parser. No network."""

from __future__ import annotations

import pytest

from dce.data.ingest.eia_rates import commercial_prices_per_kwh
from dce.data.ingest.http import IngestError
from dce.data.ingest.openei_urdb import fetch_urdb_rate, parse_urdb_item


def test_epm_parser_reads_commercial_cents() -> None:
    rows = [
        ["Census Division and State", "August 2026", "", "August 2026"],
        ["U.S. Total", "16.00", "15.00", "14.47"],
        ["California", "30.00", "29.00", "30.02"],
        ["Texas", "15.00", "14.00", "8.96"],
        ["New England", "28.31", "29.01", "22.24"],
    ]
    prices = commercial_prices_per_kwh(rows)
    assert prices["US"] == pytest.approx(0.1447)
    assert prices["CA"] == pytest.approx(0.3002)
    assert prices["TX"] == pytest.approx(0.0896)
    assert "New England" not in prices


def test_urdb_item_averages_energy_and_takes_max_demand() -> None:
    item = {
        "label": "B-10",
        "utility": "Pacific Gas & Electric Co",
        "energyratestructure": [[{"rate": 0.20}, {"rate": 0.30}], [{"rate": 0.40}]],
        "demandratestructure": [[{"rate": 10.0}], [{"rate": 20.5}]],
        "startdate": "2026-03-01",
    }
    parsed = parse_urdb_item(item, "14328")
    assert parsed.schedule == "B-10"
    assert parsed.energy_rate_kwh == pytest.approx((0.20 + 0.30 + 0.40) / 3)
    assert parsed.demand_rate_kw == pytest.approx(20.5)
    assert parsed.source == "openei"


def test_urdb_fetch_requires_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENEI_API_KEY", raising=False)
    with pytest.raises(IngestError, match="OPENEI_API_KEY"):
        fetch_urdb_rate("14328", "B-10")
