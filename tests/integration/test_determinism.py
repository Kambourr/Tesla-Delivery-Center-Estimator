"""Same inputs, same JSON. No clock and no process-order dependence."""

from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

from dce.precompute import precompute
from dce.precompute.payload import canonical_estimate_json
from dce.precompute.version import MODEL_VERSION, inputs_hash
from dce.storage.connection import get_connection
from dce.storage.repository import get_zip_result_row


def test_estimate_json_matches_across_runs_and_processes() -> None:
    # 94402 is the Kidder seed, 78701 a CBSA broker rent, 10001 a county broker rent.
    codes = ("94402", "78701", "10001")
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
        assert document["model_version"] == MODEL_VERSION
        assert document["inputs_hash"] == inputs_hash()
        assert "elapsed_ms" not in document
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
