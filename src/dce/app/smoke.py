"""Headless check for the frozen app. No window and no network.

``DeliveryCenterEstimator --smoke`` resolves 94402 and 78701 from the bundled
results database and prints one JSON object. A source checkout then compares
those documents with :func:`dce.orchestrator.estimate`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

SMOKE_ZIPS = ("94402", "78701")


def run_smoke(started: float) -> int:
    """Read the two smoke ZIPs and print timing plus the stored documents."""
    from dce.app.api import AppApi
    from dce.app.runtime import prepare_packaged_results
    from dce.precompute import result_counts

    directory, opened_from = prepare_packaged_results()
    ready = time.perf_counter()
    api = AppApi(use_repository=True, persist_cache=False, pmtiles_path=None)
    clicks: list[dict[str, object]] = []
    ok = True
    try:
        for zip_code in SMOKE_ZIPS:
            click_started = time.perf_counter()
            envelope = api.get_result(zip_code)
            click_ms = (time.perf_counter() - click_started) * 1000.0
            result = envelope.get("result")
            source = envelope.get("source")
            if (
                envelope.get("ok") is not True
                or source != "precomputed"
                or not isinstance(result, dict)
            ):
                ok = False
            clicks.append(
                {
                    "zip": zip_code,
                    "click_ms": click_ms,
                    "source": source,
                    "ok": envelope.get("ok") is True,
                    "result": result if isinstance(result, dict) else None,
                    "error": envelope.get("error"),
                }
            )
    finally:
        api.close()
    report: dict[str, object] = {
        "ok": ok,
        "opened_from": opened_from,
        "results_dir": str(directory),
        "cold_start_ms": (ready - started) * 1000.0,
        "rows": result_counts(),
        "clicks": clicks,
    }
    text = json.dumps(report, separators=(",", ":"), allow_nan=False)
    out = os.environ.get("DCE_SMOKE_OUT", "").strip()
    if out:
        Path(out).expanduser().write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if ok else 1
