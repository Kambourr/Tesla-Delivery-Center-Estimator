"""Filesystem locations for the desktop UI.

ZIP polygons come from ``data/geo``. The committed Bay Area GeoJSON is the
sample. ``data/geo/zcta_us.pmtiles`` (built by ``make zcta-boundaries``,
gitignored) is the nationwide archive when that file is present. A
precomputed dashboard document is read through
:mod:`dce.app.precomputed`, not from a table this package creates.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dce.config import bundled_seed_dir, user_data_dir

_ZCTA_ENV = "DCE_ZCTA_GEOJSON"
_PMTILES_ENV = "DCE_ZCTA_PMTILES"
_RESULTS_ENV = "DCE_UI_RESULTS_PATH"
_STYLE_ENV = "DCE_BASEMAP_STYLE"
_DEFAULT_STYLE = "vendor/basemap-style.json"
OFFLINE_BASEMAP_STYLE = "vendor/basemap-offline.json"
_PMTILES_URL = "tiles/zcta_us.pmtiles"


def web_dir() -> Path:
    """Return the bundled HTML/JS directory, including inside a PyInstaller app."""
    meipass = getattr(sys, "_MEIPASS", None)
    if isinstance(meipass, str):
        bundled = Path(meipass) / "dce" / "app" / "web"
        if bundled.is_dir():
            return bundled
    return Path(__file__).resolve().parent / "web"


def geo_dir() -> Path:
    """Return ``data/geo``, next to the bundled seed."""
    return bundled_seed_dir().parent / "geo"


def shipped_zcta_path() -> Path:
    """Return the committed Bay Area ZCTA GeoJSON."""
    return geo_dir() / "zcta_bay_area.geojson"


def zcta_geojson_path() -> Path:
    """Return the ZCTA GeoJSON the map loads when the PMTiles archive is absent.

    ``DCE_ZCTA_GEOJSON`` replaces the Bay Area sample. The sample is the
    file ``make zcta-boundaries`` writes for the nine Bay Area counties.
    """
    override = os.environ.get(_ZCTA_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return shipped_zcta_path()


def zcta_pmtiles_path() -> Path | None:
    """Return the nationwide PMTiles archive when that file exists.

    ``DCE_ZCTA_PMTILES`` names an archive. Otherwise the path is
    ``data/geo/zcta_us.pmtiles``, which ``make zcta-boundaries`` writes and
    git ignores. A missing file means the map uses the GeoJSON sample.
    """
    override = os.environ.get(_PMTILES_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() else None
    candidate = geo_dir() / "zcta_us.pmtiles"
    if candidate.is_file():
        return candidate
    return None


def zcta_pmtiles_url() -> str:
    """Return the page path the preview server uses for the archive."""
    return _PMTILES_URL


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
