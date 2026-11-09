"""Write a Folium customer-base map to HTML.

Contract
--------
``render_customer_map(geo, scored_features, out_path) -> Path``

Choropleth of catchment block groups or ZCTAs. Fill is the normalized
demand proxy (0–100). Marker at the candidate ZIP centroid. Legend.
Write ``outputs/maps/{zip}_{timestamp}.html`` (the caller chooses
``out_path``).

Basemap: prefer embedded simplified geometry with no external tile URLs so
the polygons render offline. If a tile layer is used, document that the
basemap may be blank offline. Do not download tiles in this function.

The Tkinter shell opens ``out_path`` via ``webbrowser.open``. This module
does not open a window.

Milestone M0: stub. Folium is a dependency but is not imported here yet.
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
    """Write the Folium HTML map. Not implemented in M0."""
    raise NotImplementedError("dce.geo.folium_map.render_customer_map is a stub (M0)")
