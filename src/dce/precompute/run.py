"""Fill ``zip_result`` by running ``estimate`` for many ZIPs.

The job is resumable. A ZIP whose stored ``model_version`` and
``inputs_hash`` already match is left in place. ``--retry-errors`` estimates
again a ZIP that previously failed for a data reason. ZIPs that still cannot
be estimated are stored with ``status = error`` and a reason. They do not
abort the batch.

Workers do not share a SQLite connection. Each process opens the database,
builds the in-memory demand index once, and returns JSON. The parent writes
the rows.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dce.config import user_data_dir
from dce.data.national_demand import ZipPlace
from dce.orchestrator import warm_bundle
from dce.precompute.payload import BAY_AREA_COUNTIES, canonical_json, payload_for_zip
from dce.precompute.version import MODEL_VERSION, inputs_hash
from dce.storage.connection import get_connection
from dce.storage.repository import (
    ZipResultRecord,
    get_zip_result_row,
    get_zip_result_rows,
    list_fresh_zip_results,
    upsert_zip_results,
)


@dataclass(frozen=True)
class PrecomputeReport:
    """Timing and row counts for one precompute invocation."""

    requested: int
    computed: int
    skipped: int
    errors: int
    elapsed_seconds: float
    zips_per_second: float
    projected_full_seconds: float | None
    resolvable_zips: int
    db_bytes: int
    model_version: str
    inputs_hash: str


def precompute(
    *,
    data_dir: Path | None = None,
    sample: str | None = None,
    limit: int | None = None,
    workers: int | None = None,
    retry_errors: bool = False,
    zip_codes: Sequence[str] | None = None,
) -> PrecomputeReport:
    """Estimate the requested ZIPs and store one row each.

    ``sample='bay-area'`` keeps the nine Bay Area counties. ``zip_codes``
    estimates that list instead. ``limit`` stops after that many ZIPs.
    """
    if sample not in {None, "bay-area"}:
        raise ValueError("sample must be 'bay-area' or omitted.")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1.")
    directory = user_data_dir() if data_dir is None else data_dir
    bundle = warm_bundle(directory)
    conn = get_connection(directory)
    selected = _select(bundle.demand.places, sample=sample, limit=limit, zip_codes=zip_codes)
    version = MODEL_VERSION
    digest = inputs_hash()
    fresh = list_fresh_zip_results(
        conn, model_version=version, inputs_hash=digest, include_errors=not retry_errors
    )
    pending = [code for code in selected if code not in fresh]
    started = time.perf_counter()
    errors = 0
    computed = 0
    worker_count = _workers(workers, len(pending))
    if pending and worker_count <= 1:
        computed, errors = _run_inline(conn, directory, pending)
    elif pending:
        computed, errors = _run_pool(conn, directory, pending, worker_count)
    elapsed = time.perf_counter() - started
    rate = computed / elapsed if elapsed > 0.0 and computed else 0.0
    resolvable = len(bundle.demand.places)
    projected = resolvable / rate if rate > 0.0 else None
    conn.close()
    return PrecomputeReport(
        requested=len(selected),
        computed=computed,
        skipped=len(selected) - len(pending),
        errors=errors,
        elapsed_seconds=elapsed,
        zips_per_second=rate,
        projected_full_seconds=projected,
        resolvable_zips=resolvable,
        db_bytes=_db_bytes(directory),
        model_version=version,
        inputs_hash=digest,
    )


def get_zip_result(zip_code: str, *, data_dir: Path | None = None) -> dict[str, object] | None:
    """Return the stored JSON for one ZIP, or ``None`` when it has not been stored."""
    code = zip_code.strip()
    conn = get_connection(user_data_dir() if data_dir is None else data_dir)
    try:
        row = get_zip_result_row(conn, code)
    finally:
        conn.close()
    if row is None:
        return None
    return _with_current(row.payload_json, row.model_version, row.inputs_hash)


def get_zip_results(
    zip_codes: Sequence[str], *, data_dir: Path | None = None
) -> dict[str, dict[str, object]]:
    """Return stored JSON for the ZIPs that have a row, in request order."""
    conn = get_connection(user_data_dir() if data_dir is None else data_dir)
    try:
        rows = get_zip_result_rows(conn, [code.strip() for code in zip_codes])
    finally:
        conn.close()
    found = {
        row.zip_code: _with_current(row.payload_json, row.model_version, row.inputs_hash)
        for row in rows
    }
    return {code.strip(): found[code.strip()] for code in zip_codes if code.strip() in found}


def format_report(report: PrecomputeReport) -> str:
    """Return the human timing summary."""
    projected = (
        "n/a" if report.projected_full_seconds is None else _seconds(report.projected_full_seconds)
    )
    return "\n".join(
        [
            f"Precompute {report.model_version}",
            f"  Inputs hash: {report.inputs_hash}",
            f"  Requested: {report.requested:,}",
            f"  Computed: {report.computed:,}",
            f"  Skipped (fresh): {report.skipped:,}",
            f"  Errors stored: {report.errors:,}",
            f"  Elapsed: {_seconds(report.elapsed_seconds)}",
            f"  Rate: {report.zips_per_second:,.2f} ZIP/s",
            f"  Resolvable ZIPs: {report.resolvable_zips:,}",
            f"  Projected full run: {projected}",
            f"  Results database: {report.db_bytes:,} bytes",
        ]
    )


def _select(
    places: dict[str, ZipPlace],
    *,
    sample: str | None,
    limit: int | None,
    zip_codes: Sequence[str] | None,
) -> list[str]:
    if zip_codes is not None:
        codes = [code.strip() for code in zip_codes if code.strip() in places]
    else:
        codes = []
        for code in sorted(places):
            place = places[code]
            if sample == "bay-area" and place.county_fips not in BAY_AREA_COUNTIES:
                continue
            codes.append(code)
    if limit is not None:
        return codes[:limit]
    return codes


def _run_inline(conn: sqlite3.Connection, directory: Path, pending: list[str]) -> tuple[int, int]:
    computed = 0
    errors = 0
    batch: list[ZipResultRecord] = []
    for code in pending:
        record, failed = _record(code, directory)
        batch.append(record)
        computed += 1
        errors += int(failed)
        if len(batch) >= 25:
            upsert_zip_results(conn, batch)
            batch = []
    if batch:
        upsert_zip_results(conn, batch)
    return computed, errors


def _run_pool(
    conn: sqlite3.Connection, directory: Path, pending: list[str], workers: int
) -> tuple[int, int]:
    ctx = multiprocessing.get_context("spawn")
    computed = 0
    errors = 0
    batch: list[ZipResultRecord] = []
    with ctx.Pool(processes=workers, initializer=_worker_init, initargs=(str(directory),)) as pool:
        for code, payload, elapsed, failed in pool.imap_unordered(
            _worker_zip, pending, chunksize=4
        ):
            batch.append(_record_from_payload(code, payload, elapsed))
            computed += 1
            errors += int(failed)
            if len(batch) >= 25:
                upsert_zip_results(conn, batch)
                batch = []
                print(
                    f"precompute: {computed:,} computed, {errors:,} errors",
                    flush=True,
                )
    if batch:
        upsert_zip_results(conn, batch)
    return computed, errors


def _record(code: str, directory: Path) -> tuple[ZipResultRecord, bool]:
    started = time.perf_counter()
    payload = payload_for_zip(code, data_dir=directory)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    failed = payload.get("status") == "error"
    return _record_from_payload(code, canonical_json(payload), elapsed_ms), failed


def _record_from_payload(code: str, payload: str, elapsed_ms: float) -> ZipResultRecord:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        parsed = {"status": "error", "reason": "Payload was not an object."}
    if parsed.get("schema") == "dce.ui_result.v1":
        status = "ok"
    else:
        status = str(parsed.get("status", "error"))
    reason = parsed.get("reason")
    return ZipResultRecord(
        zip_code=code,
        model_version=str(parsed.get("model_version", MODEL_VERSION)),
        inputs_hash=str(parsed.get("inputs_hash", inputs_hash())),
        status=status if status in {"ok", "error"} else "error",
        reason=None if reason is None else str(reason),
        payload_json=payload if isinstance(payload, str) else json.dumps(parsed),
        computed_at=str(parsed.get("computed_at", "")),
        elapsed_ms=elapsed_ms,
    )


_WORKER_DIR: str | None = None


def _worker_init(data_dir: str) -> None:
    global _WORKER_DIR
    _WORKER_DIR = data_dir
    warm_bundle(Path(data_dir))


def _worker_zip(zip_code: str) -> tuple[str, str, float, bool]:
    started = time.perf_counter()
    directory = Path(_WORKER_DIR) if _WORKER_DIR else user_data_dir()
    payload = payload_for_zip(zip_code, data_dir=directory)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    failed = payload.get("status") == "error"
    return zip_code, canonical_json(payload), elapsed_ms, bool(failed)


def _workers(requested: int | None, pending: int) -> int:
    if pending <= 0:
        return 1
    if requested is not None:
        if requested < 1:
            raise ValueError("workers must be >= 1.")
        return requested
    if pending < 32:
        return 1
    count = os.cpu_count() or 1
    return max(1, min(count, pending))


def _with_current(payload: str, model_version: str, digest: str) -> dict[str, object]:
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        return {"status": "error", "reason": "Stored payload was not an object."}
    body = {str(key): value for key, value in parsed.items()}
    body["current"] = model_version == MODEL_VERSION and digest == inputs_hash()
    return body


def _db_bytes(directory: Path) -> int:
    total = 0
    for name in ("dce.sqlite", "dce.sqlite-wal", "dce.sqlite-shm"):
        path = directory / name
        if path.is_file():
            total += path.stat().st_size
    return total


def _seconds(value: float) -> str:
    if value < 60.0:
        return f"{value:.2f}s"
    minutes, seconds = divmod(value, 60.0)
    return f"{int(minutes)}m {seconds:.1f}s"
