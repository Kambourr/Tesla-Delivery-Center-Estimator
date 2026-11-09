"""Paths, source TTLs, and default-assumption locations.

Contract
--------
Resolve filesystem locations. Do not fetch data and do not compute cost.
Looking up a path does not create it. :func:`dce.storage.connection.get_connection`
creates the database directory when a caller opens the database.

User database:

- macOS: ``~/Library/Application Support/DeliveryCenterEstimator/dce.sqlite``
- Windows: ``%LOCALAPPDATA%/DeliveryCenterEstimator/dce.sqlite``
- Linux (development): ``~/.local/share/delivery-center-estimator/dce.sqlite``

These are the ADR-0002 directories. On macOS they match
``platformdirs.user_data_dir("DeliveryCenterEstimator", appauthor=False)``.
On Windows they match that call when ``LOCALAPPDATA`` is set. Linux keeps
the hyphenated directory name from the architecture doc, so this module
does not ask platformdirs to use one app name on every OS.

Bundled seed lives in the repository (and later inside the ``.app``) at
``data/seed/``. First launch must work offline by copying that seed into
the user database. Assumption defaults will live at
``data/defaults/assumptions.yaml``.

Per-source refresh cadences and stale thresholds are specified in
``docs/DATA_SOURCES.md``. This module will expose them as data. It does not
decide staleness; ``dce.data.registry.staleness_status`` does.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DB_FILENAME = "dce.sqlite"
_MACOS_DIR_NAME = "DeliveryCenterEstimator"
_WINDOWS_DIR_NAME = "DeliveryCenterEstimator"
_LINUX_DIR_NAME = "delivery-center-estimator"


class ConfigError(Exception):
    """The project layout could not be resolved."""


def user_data_dir() -> Path:
    """Return the per-user application directory for this OS.

    Does not create the directory. Apple Silicon and Intel Macs share the
    macOS path; the ``.app`` build is what is Apple Silicon specific.
    """
    # A local str keeps mypy from constant-folding sys.platform. On a Mac
    # runner that fold marks the Windows and Linux returns unreachable.
    platform = sys.platform
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _MACOS_DIR_NAME
    if platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        if local:
            return Path(local) / _WINDOWS_DIR_NAME
        return Path.home() / "AppData" / "Local" / _WINDOWS_DIR_NAME
    return Path.home() / ".local" / "share" / _LINUX_DIR_NAME


def user_db_path() -> Path:
    """Return ``dce.sqlite`` inside :func:`user_data_dir`."""
    return user_data_dir() / DB_FILENAME


def bundled_seed_dir() -> Path:
    """Return the repository ``data/seed`` directory."""
    return _project_root() / "data" / "seed"


def assumptions_path() -> Path:
    """Return ``data/defaults/assumptions.yaml`` (the file arrives in a later milestone)."""
    return _project_root() / "data" / "defaults" / "assumptions.yaml"


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "data" / "seed").is_dir():
            return parent
    raise ConfigError("Could not find the project root containing pyproject.toml and data/seed.")
