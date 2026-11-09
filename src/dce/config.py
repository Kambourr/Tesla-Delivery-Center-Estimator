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
``docs/DATA_SOURCES.md``. Staleness is decided by
``dce.data.registry.staleness_status``. This module does not fetch data.

``api_key`` reads a named public-data key from the environment, then from a
local ``.env`` at the project root. It never logs the value. A missing key
is ``None``.
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


def demo_data_dir() -> Path:
    """Return the repository ``data/demo`` directory. Does not create it."""
    return _project_root() / "data" / "demo"


def api_key(name: str) -> str | None:
    """Return one public-data API key, or ``None`` when it is unset.

    The process environment wins over a local ``.env``. The value is not logged.
    """
    if not name.isidentifier():
        raise ConfigError(f"API key name must be an identifier, got {name!r}.")
    load_local_env()
    value = os.environ.get(name, "").strip()
    return value or None


def load_local_env() -> None:
    """Copy unset keys from the project ``.env`` into the process environment.

    Existing variables are left alone. A missing file is a no-op. Lines that
    are blank, comments, or not ``NAME=value`` are ignored.
    """
    try:
        path = _project_root() / ".env"
    except ConfigError:
        return
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in os.environ:
            os.environ[key] = value


def _parse_env_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if text == "" or text.startswith("#"):
        return None
    if text.startswith("export "):
        text = text.removeprefix("export ").strip()
    if "=" not in text:
        return None
    name, raw = text.split("=", 1)
    name = name.strip()
    if not name.isidentifier():
        return None
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return name, value


def bundle_root() -> Path | None:
    """Return PyInstaller's extraction directory when this process is frozen.

    ``sys._MEIPASS`` is set only inside a packaged app. The spec copies
    ``data/seed`` there. A checkout has no ``_MEIPASS``, so this returns
    ``None`` and callers walk up to ``pyproject.toml`` instead.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if not isinstance(meipass, str) or not meipass:
        return None
    root = Path(meipass)
    if (root / "data" / "seed").is_dir():
        return root
    return None


def _project_root() -> Path:
    bundled = bundle_root()
    if bundled is not None:
        return bundled
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "data" / "seed").is_dir():
            return parent
    raise ConfigError("Could not find the project root containing pyproject.toml and data/seed.")
