"""Model version and inputs hash for stored ZIP results.

A row is stale when either value differs from the process that is about to
read or write it. The version is a code constant. The hash covers the public
files that change a number: assumptions, the operating-rate demo, and the
seed extracts the catchment reads.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from dce.config import assumptions_path, bundled_seed_dir, demo_data_dir

MODEL_VERSION = "2026.11.4-rent-ladder"

_HASH_FILES = (
    "coverage.json",
    "zev_zip_sales.csv",
    "zev_county_sales.csv",
    "zcta_acs_2024.csv",
    "zcta_centroid_2024.csv",
    "zip_crosswalk.csv",
    "oews_metro_2025.csv",
    "rent_cbsa.csv",
    "rent_model_coeffs.json",
)

_CACHE: dict[str, str] = {}


def inputs_hash() -> str:
    """Return the sha256 of the public inputs this model version reads."""
    cached = _CACHE.get(MODEL_VERSION)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    digest.update(MODEL_VERSION.encode("utf-8"))
    _file(digest, assumptions_path())
    _file(digest, demo_data_dir() / "san_mateo" / "operating_inputs.json")
    seed = bundled_seed_dir()
    for name in _HASH_FILES:
        _file(digest, seed / name)
    cached = digest.hexdigest()
    _CACHE[MODEL_VERSION] = cached
    return cached


def _file(digest: hashlib._Hash, path: Path) -> None:
    digest.update(path.name.encode("utf-8"))
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
    except OSError as exc:
        raise FileNotFoundError(f"Inputs hash could not read {path}.") from exc
