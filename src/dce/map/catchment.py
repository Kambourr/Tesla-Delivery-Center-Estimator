"""Catchment polygons around a candidate ZIP.

Contract
--------
Build the set of block groups (preferred) or ZCTAs within
``catchment_miles`` (default 15) of the ZIP centroid using geopandas
distance. Score each feature with the demand proxy (0–100) for the
choropleth. Read geometries from the local demo GeoPackage or from SQLite.
No network.

Milestone M0: stub. Does not import geopandas at runtime, so importing this
module does not load the geo stack.
"""

from __future__ import annotations

from dce.model.types import GeoContext


def catchment_features(geo: GeoContext, radius_miles: float):
    """Return scored catchment features. Not implemented in M0."""
    raise NotImplementedError("dce.map.catchment.catchment_features is a stub (M0)")
