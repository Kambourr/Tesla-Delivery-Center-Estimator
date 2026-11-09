"""pywebview ``js_api`` for the map.

JavaScript calls :meth:`bootstrap`, :meth:`get_result`, and :meth:`compare`.
A result is read from a precomputed file or from
:func:`dce.app.precomputed.lookup_zip_result` (the forthcoming
``get_zip_result`` / ``get_zip_results`` API). Otherwise
:func:`dce.app.results.build_ui_result` runs on a worker thread, and the
value is cached for the rest of the process. The page shows a skeleton
while that call is in flight. The second request for the same ZIP does not
compute again.

Importing this module does not import pywebview and does not open a window.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Lock

from dce.app.mapdata import (
    MapDataError,
    load_centers,
    load_zcta,
    nationwide_zip_index,
    zip_index,
)
from dce.app.paths import (
    OFFLINE_BASEMAP_STYLE,
    shipped_zcta_path,
    zcta_pmtiles_path,
    zcta_pmtiles_url,
)
from dce.app.precomputed import lookup_zip_result
from dce.app.results import (
    UI_COMPARE_SCHEMA,
    UI_MAP_SCHEMA,
    UI_RESULT_SCHEMA,
    build_ui_result,
    compare_metrics,
)
from dce.data.catchment_demand import CatchmentDemandError
from dce.data.operating_inputs import OperatingInputError
from dce.geo.resolve import InvalidZipError, UnknownZipError
from dce.model.errors import ModelError
from dce.orchestrator import EstimateDataError

Reader = Callable[[str], object]
_DISCOVER = object()


class AppApi:
    """Methods exposed to the page. Names that start with ``_`` stay private."""

    def __init__(
        self,
        *,
        zcta_path: Path | None = None,
        results_path: Path | None = None,
        cache_dir: Path | None = None,
        persist_cache: bool = False,
        basemap_style: str = "vendor/basemap-style.json",
        precomputed_reader: Reader | None = None,
        use_repository: bool = False,
        pmtiles_path: Path | None | object = _DISCOVER,
    ) -> None:
        self._zcta_path = shipped_zcta_path() if zcta_path is None else zcta_path
        self._results_path = results_path
        self._cache_dir = cache_dir
        self._persist_cache = persist_cache and cache_dir is not None
        self._basemap_style = basemap_style
        self._reader = precomputed_reader
        self._use_repository = use_repository
        if pmtiles_path is _DISCOVER:
            self._pmtiles_path = zcta_pmtiles_path()
        elif isinstance(pmtiles_path, Path):
            self._pmtiles_path = pmtiles_path
        else:
            self._pmtiles_path = None
        self._memory: dict[str, dict[str, object]] = {}
        self._inflight: dict[str, Future[dict[str, object]]] = {}
        self._lock = Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dce-ui")
        self._closed = False

    def close(self) -> None:
        """Stop the worker pool. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)

    def bootstrap(self) -> dict[str, object]:
        """Return ZIP polygons, center markers, and the basemap style path."""
        try:
            zcta = load_zcta(self._zcta_path)
            centers = [dict(row) for row in load_centers()]
        except (OSError, MapDataError) as exc:
            return _fail("map_failed", str(exc))
        tiles = self._pmtiles_path is not None and self._pmtiles_path.is_file()
        return {
            "ok": True,
            "schema": UI_MAP_SCHEMA,
            "zcta": zcta,
            "zip_index": nationwide_zip_index() if tiles else zip_index(zcta),
            "centers": centers,
            "basemap_style": self._basemap_style,
            "basemap_fallback": OFFLINE_BASEMAP_STYLE,
            "zcta_name": self._zcta_path.name,
            "boundaries": {
                "mode": "pmtiles" if tiles else "geojson",
                "pmtiles": zcta_pmtiles_url() if tiles else None,
                "source_layer": "zcta",
                "id_property": "zcta",
                "minzoom": 3,
                "maxzoom": 8,
            },
        }

    def get_result(self, zip_code: str) -> dict[str, object]:
        """Return one dashboard document, computing on a worker when needed.

        ``source`` is ``precomputed`` or ``computed`` the first time, and
        ``cache`` after that. Failures are ``ok: false`` and are not cached.
        """
        try:
            key = _normalize(zip_code)
        except InvalidZipError as exc:
            return _fail("invalid_zip", str(exc))
        return self._ensure(key).result()

    def compare(self, zip_a: str, zip_b: str) -> dict[str, object]:
        """Return both dashboard documents and which value is better."""
        try:
            left_key = _normalize(zip_a)
            right_key = _normalize(zip_b)
        except InvalidZipError as exc:
            return _fail("invalid_zip", str(exc))
        if left_key == right_key:
            return _fail("invalid_zip", "Pick two different ZIPs to compare.")
        left_future = self._ensure(left_key)
        right_future = self._ensure(right_key)
        left = left_future.result()
        right = right_future.result()
        if left.get("ok") is not True or right.get("ok") is not True:
            return {
                "ok": False,
                "error": {
                    "code": "estimate_failed",
                    "message": "One of the ZIPs could not be estimated.",
                },
                "a": left,
                "b": right,
            }
        left_result = _result_dict(left)
        right_result = _result_dict(right)
        return {
            "ok": True,
            "schema": UI_COMPARE_SCHEMA,
            "a": left_result,
            "b": right_result,
            "metrics": compare_metrics(left_result, right_result),
        }

    def _ensure(self, key: str) -> Future[dict[str, object]]:
        ready = self._ready(key)
        if ready is not None:
            future: Future[dict[str, object]] = Future()
            future.set_result(ready)
            return future
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                return existing
            future = self._pool.submit(self._compute, key)
            self._inflight[key] = future
            return future

    def _ready(self, key: str) -> dict[str, object] | None:
        with self._lock:
            cached = self._memory.get(key)
        if cached is not None:
            return _ok("cache", cached)
        precomputed = self._read_precomputed(key)
        if precomputed is not None:
            self._remember(key, precomputed)
            return _ok("precomputed", precomputed)
        stored = self._read_disk(key)
        if stored is not None:
            self._remember(key, stored)
            return _ok("cache", stored)
        return None

    def _compute(self, key: str) -> dict[str, object]:
        try:
            ready = self._ready(key)
            if ready is not None:
                return ready
            try:
                payload = build_ui_result(key)
            except UnknownZipError as exc:
                return _fail("unknown_zip", str(exc))
            except (
                EstimateDataError,
                OperatingInputError,
                CatchmentDemandError,
                ModelError,
                MapDataError,
            ) as exc:
                return _fail("estimate_failed", str(exc))
            except Exception as exc:
                return _fail("estimate_failed", str(exc))
            self._remember(key, payload)
            self._write_disk(key, payload)
            return _ok("computed", payload)
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def _remember(self, key: str, payload: dict[str, object]) -> None:
        with self._lock:
            self._memory[key] = payload

    def _read_precomputed(self, key: str) -> dict[str, object] | None:
        if self._reader is not None:
            found = _accept(self._reader(key), key)
            if found is not None:
                return found
        found = _read_results_path(self._results_path, key)
        if found is not None:
            return found
        if self._use_repository:
            return _read_repository(key)
        return None

    def _read_disk(self, key: str) -> dict[str, object] | None:
        if self._cache_dir is None:
            return None
        path = self._cache_dir / f"{key}.json"
        if not path.is_file():
            return None
        return _accept(_load_json(path), key)

    def _write_disk(self, key: str, payload: dict[str, object]) -> None:
        if not self._persist_cache or self._cache_dir is None:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            (self._cache_dir / f"{key}.json").write_text(
                json.dumps(payload),
                encoding="utf-8",
            )
        except OSError:
            return


def _normalize(zip_code: str) -> str:
    text = str(zip_code).strip()
    if len(text) != 5 or not text.isdigit():
        raise InvalidZipError(zip_code)
    return text


def _ok(source: str, result: dict[str, object]) -> dict[str, object]:
    return {"ok": True, "source": source, "result": result}


def _fail(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _result_dict(envelope: dict[str, object]) -> dict[str, object]:
    result = envelope.get("result")
    if not isinstance(result, dict):
        return {}
    return {str(key): value for key, value in result.items()}


def _accept(payload: object, zip_code: str) -> dict[str, object] | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema") != UI_RESULT_SCHEMA or payload.get("zip_code") != zip_code:
        return None
    return {str(key): value for key, value in payload.items()}


def _read_results_path(path: Path | None, zip_code: str) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    if path.is_dir():
        return _accept(_load_json(path / f"{zip_code}.json"), zip_code)
    loaded = _load_json(path)
    if not isinstance(loaded, dict):
        return None
    direct = _accept(loaded, zip_code)
    if direct is not None:
        return direct
    return _accept(loaded.get(zip_code), zip_code)


def _load_json(path: Path) -> object:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_repository(zip_code: str) -> dict[str, object] | None:
    """Ask the precompute adapter. A miss means the ZIP is computed."""
    return _accept(lookup_zip_result(zip_code), zip_code)
