"""Catchment polygons around a candidate ZIP.

Contract
--------
Build the set of block groups (preferred) or ZCTAs within
``catchment_miles`` (default 15) of the ZIP centroid using geopandas
distance. Score each feature with the demand proxy (0–100) for the
choropleth. The caller supplies geometries (a demo GeoPackage or rows
storage already loaded). No network and no SQL in this module.

Milestone M0: stub. Does not import geopandas at runtime, so importing this
module does not load the geo stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dce.model.types import GeoContext

if TYPE_CHECKING:
    import geopandas as gpd


def catchment_features(geo: GeoContext, radius_miles: float) -> gpd.GeoDataFrame:
    """Return scored catchment features. Not implemented in M0."""
    raise NotImplementedError("dce.geo.catchment.catchment_features is a stub (M0)")
