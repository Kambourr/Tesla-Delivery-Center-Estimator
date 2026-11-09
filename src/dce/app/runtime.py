"""Locate the precomputed results database for a packaged app.

A checkout keeps using the per-user directory from ADR-0002. A frozen app
opens the bundled ``dce.sqlite`` read-only from ``sys._MEIPASS``. When that
open cannot be done without writing a journal, the file is copied once to
``~/Library/Application Support/DCE/`` and that copy is opened read-only.

This module does not run SQL. :mod:`dce.storage` answers whether the file
can be read, and :func:`dce.precompute.get_zip_result` reads the rows.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from dce.config import DB_FILENAME, bundle_root, user_data_dir
from dce.storage.connection import can_open_readonly

_PREPARED = "DCE_RESULTS_PREPARED"
_DIR = "DCE_RESULTS_DIR"
_READONLY = "DCE_RESULTS_READONLY"
_OPENED = "DCE_RESULTS_OPENED_FROM"
_SUPPORT_NAME = "DCE"


def packaged_support_dir() -> Path:
    """Return the first-launch copy directory for the bundled results database.

    On macOS this is ``~/Library/Application Support/DCE``. The ADR-0002
    directory (``DeliveryCenterEstimator``) stays the writable user database
    for a checkout. The packaged results file is a separate read-only copy.
    """
    platform = sys.platform
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _SUPPORT_NAME
    if platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / _SUPPORT_NAME
    return Path.home() / ".local" / "share" / "dce"


def bundled_results_db() -> Path | None:
    """Return the results database shipped inside a frozen app, if it is there."""
    root = bundle_root()
    if root is None:
        return None
    path = root / "data" / "results" / DB_FILENAME
    return path if path.is_file() else None


def prepare_packaged_results() -> tuple[Path, str]:
    """Point later reads at the bundled database and return ``(directory, opened_from)``.

    ``opened_from`` is ``meipass``, ``application_support``, or ``user``.
    A second call in the same process returns the first choice.
    """
    if os.environ.get(_PREPARED) == "1":
        raw = os.environ.get(_DIR, "").strip()
        opened = os.environ.get(_OPENED, "user")
        if raw:
            return Path(raw).expanduser(), opened
    bundled = bundled_results_db()
    if bundled is None:
        return user_data_dir(), "user"
    if can_open_readonly(bundled):
        return _activate(bundled.parent, "meipass")
    dest_dir = packaged_support_dir()
    dest = dest_dir / DB_FILENAME
    if not dest.is_file() or dest.stat().st_size != bundled.stat().st_size:
        _copy_database(bundled, dest)
    if not can_open_readonly(dest):
        raise RuntimeError(f"Copied results database cannot be opened read-only: {dest}")
    return _activate(dest_dir, "application_support")


def _activate(directory: Path, opened_from: str) -> tuple[Path, str]:
    os.environ[_DIR] = str(directory)
    os.environ[_READONLY] = "1"
    os.environ[_OPENED] = opened_from
    os.environ[_PREPARED] = "1"
    return directory, opened_from


def _copy_database(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(dest.name + ".partial")
    shutil.copyfile(source, temporary)
    temporary.replace(dest)
