"""Filesystem locations for the desktop UI.

The ZCTA shapes, the basemap style, and a precomputed-results file are
configurable so other work can land without editing this package. The
shipped Bay Area GeoJSON is the default until that file exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dce.config import user_data_dir

_ZCTA_ENV = "DCE_ZCTA_GEOJSON"
_RESULTS_ENV = "DCE_UI_RESULTS_PATH"
_STYLE_ENV = "DCE_BASEMAP_STYLE"
_DEFAULT_STYLE = "vendor/basemap-style.json"


def web_dir() -> Path:
    """Return the bundled HTML/JS directory, including inside a PyInstaller app."""
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str):
        bundled = Path(meipass) / "dce" / "app" / "web"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent / "web"


def shipped_zcta_path() -> Path:
    """Return the Bay Area ZCTA GeoJSON that ships with the app."""
    return web_dir() / "fixtures" / "bay_area_zcta.geojson"


def zcta_geojson_path() -> Path:
    """Return the ZCTA file the map should load.

    ``DCE_ZCTA_GEOJSON`` replaces the shipped fixture. The national extract
    should set that variable. A missing override falls back to the fixture.
    """
    override = os.environ.get(_ZCTA_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return shipped_zcta_path()


def basemap_style() -> str:
    """Return the MapLibre style URL or the bundled relative style path.

    ``DCE_BASEMAP_STYLE`` may be an ``https`` style document or a path the
    page can request. The default is the local dark style. That file is
    bundled; its tiles are fetched at runtime and may be absent offline.
    """
    override = os.environ.get(_STYLE_ENV, "").strip()
    return override or _DEFAULT_STYLE


def ui_results_path() -> Path | None:
    """Return a precomputed UI-results file or directory, if one is configured.

    ``DCE_UI_RESULTS_PATH`` wins. Otherwise
    ``<user data>/ui_results`` is used when that path already exists. The
    directory is not created here.
    """
    override = os.environ.get(_RESULTS_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    default = user_data_dir() / "ui_results"
    if default.exists():
        return default
    return None


def ui_cache_dir() -> Path:
    """Return the per-user cache directory for results this process computed."""
    return user_data_dir() / "ui_cache"
