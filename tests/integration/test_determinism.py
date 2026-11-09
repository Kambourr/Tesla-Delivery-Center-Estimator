"""Same inputs, same JSON. No clock and no process-order dependence."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from dce.app.results import COMPUTED_AT
from dce.precompute import get_zip_result, precompute
from dce.precompute.payload import canonical_estimate_json
from dce.precompute.version import MODEL_VERSION, inputs_hash
from dce.storage.connection import get_connection
from dce.storage.repository import get_zip_result_row


def test_estimate_json_matches_across_runs_and_processes() -> None:
    # 94402 Kidder seed, 78701 CBSA broker rent, 10001 county broker rent, 82401 no broker row.
    codes = ("94402", "78701", "10001", "82401")
    first = {code: canonical_estimate_json(code) for code in codes}
    second = {code: canonical_estimate_json(code) for code in codes}
    assert first == second
    context = multiprocessing.get_context("spawn")
    with context.Pool(1) as pool:
        remote = pool.map(canonical_estimate_json, list(codes))
    assert remote == [first[code] for code in codes]


def test_precompute_json_matches_inline_and_multiprocessing(tmp_path: Path) -> None:
    codes = ("94402", "78701", "10001")
    inline_a = tmp_path / "inline-a"
    inline_b = tmp_path / "inline-b"
    pooled = tmp_path / "pooled"
    precompute(data_dir=inline_a, zip_codes=codes, workers=1)
    precompute(data_dir=inline_b, zip_codes=codes, workers=1)
    precompute(data_dir=pooled, zip_codes=codes, workers=2)
    left = _payloads(inline_a, codes)
    again = _payloads(inline_b, codes)
    right = _payloads(pooled, codes)
    assert left == again == right
    for code, text in left.items():
        document = json.loads(text)
        assert document["schema"] == "dce.ui_result.v1"
        assert document["zip_code"] == code
        assert "model_version" not in document
        assert "inputs_hash" not in document
        assert "computed_at" not in document
        assert "elapsed_ms" not in document
        served = get_zip_result(code, data_dir=inline_a)
        assert served is not None
        assert served["model_version"] == MODEL_VERSION
        assert served["inputs_hash"] == inputs_hash()
        assert served["computed_at"] == COMPUTED_AT
    conn = get_connection(inline_a)
    try:
        for code in codes:
            row = get_zip_result_row(conn, code)
            assert row is not None
            assert row.status == "ok"
            assert row.model_version == MODEL_VERSION
            assert row.inputs_hash == inputs_hash()
            assert row.payload_json == left[code]
    finally:
        conn.close()


def _payloads(directory: Path, codes: tuple[str, ...]) -> dict[str, str]:
    conn = get_connection(directory)
    try:
        found: dict[str, str] = {}
        for code in codes:
            row = get_zip_result_row(conn, code)
            assert row is not None
            found[code] = row.payload_json
        return found
    finally:
        conn.close()


def test_local_cost_ladders_are_stable_across_processes() -> None:
    codes = ("10001", "94402", "78701", "33139", "82401", "10601", "07601")
    first = [_local_cost_key(code) for code in codes]
    assert first == [_local_cost_key(code) for code in codes]
    context = multiprocessing.get_context("spawn")
    with context.Pool(2) as pool:
        remote = pool.map(_local_cost_key, list(codes))
    assert remote == first


def _local_cost_key(code: str) -> tuple[str, str, float, str, str, float]:
    from dce.data.construction_cost import resolve_construction_cost
    from dce.data.property_tax import resolve_property_tax
    from dce.geo.resolve import resolve_zip

    geo = resolve_zip(code)
    tax = resolve_property_tax(geo)
    cost = resolve_construction_cost(geo)
    return (
        tax.tier,
        tax.place,
        tax.effective_rate,
        cost.tier,
        cost.geography_id,
        cost.fitout_index,
    )
