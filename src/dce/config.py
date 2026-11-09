"""Paths, source TTLs, and default-assumption locations.

Contract
--------
Resolve filesystem locations. Do not fetch data and do not compute cost.

User database (created by a later milestone, not by import):

- macOS: ``~/Library/Application Support/DeliveryCenterEstimator/dce.sqlite``
- Windows: ``%LOCALAPPDATA%/DeliveryCenterEstimator/dce.sqlite``
- Linux (development): ``~/.local/share/delivery-center-estimator/dce.sqlite``

Bundled seed lives in the repository (and later inside the ``.app``) at
``data/seed/``. First launch must work offline by copying that seed into
the user database. Assumption defaults will live at
``data/defaults/assumptions.yaml``.

Per-source refresh cadences and stale thresholds are specified in
``docs/DATA_SOURCES.md``. This module will expose them as data. It does not
decide staleness; ``dce.data.registry.staleness_status`` does.

Milestone M0: path helpers raise ``NotImplementedError``. No directories
are created at import time.
"""

from __future__ import annotations

from pathlib import Path


def user_data_dir() -> Path:
    """Return the per-user application directory for this OS. Not implemented in M0."""
    raise NotImplementedError("dce.config.user_data_dir is a stub (M0)")


def user_db_path() -> Path:
    """Return the user SQLite path (``dce.sqlite`` inside :func:`user_data_dir`)."""
    raise NotImplementedError("dce.config.user_db_path is a stub (M0)")


def bundled_seed_dir() -> Path:
    """Return the packaged ``data/seed`` directory. Not implemented in M0."""
    raise NotImplementedError("dce.config.bundled_seed_dir is a stub (M0)")


def assumptions_path() -> Path:
    """Return ``data/defaults/assumptions.yaml``. Not implemented in M0."""
    raise NotImplementedError("dce.config.assumptions_path is a stub (M0)")
