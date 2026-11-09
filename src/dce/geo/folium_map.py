"""Retired Folium stub.

The desktop map is MapLibre in ``dce.app`` (ADR-0006). Nothing on the
estimate or precompute path imports this module. ``render_customer_map``
remains so older imports fail with ``NotImplementedError`` instead of
``ImportError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dce.model.types import GeoContext

if TYPE_CHECKING:
    import geopandas as gpd


def render_customer_map(
    geo: GeoContext,
    scored_features: gpd.GeoDataFrame,
    out_path: Path,
) -> Path:
    """Retired. The desktop map is ``dce.app``."""
    raise NotImplementedError("dce.geo.folium_map.render_customer_map is a stub (M0)")
