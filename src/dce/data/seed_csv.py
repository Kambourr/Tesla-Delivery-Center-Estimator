"""Read one bundled seed CSV. No network and no SQLite."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from dce.config import bundled_seed_dir


class PublicSeedError(ValueError):
    """A bundled public-data seed is missing or malformed."""


@lru_cache(maxsize=16)
def read_seed_csv(name: str) -> tuple[dict[str, str], ...]:
    """Return every data row of ``data/seed/<name>``."""
    path = bundled_seed_dir() / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PublicSeedError(f"Could not read seed {name}.") from exc
    rows = tuple(csv.DictReader(text.splitlines()))
    if not rows:
        raise PublicSeedError(f"Seed {name} has no rows.")
    return rows


def seed_path(name: str) -> Path:
    """Return the path of a bundled seed file. Does not check that it exists."""
    return bundled_seed_dir() / name
