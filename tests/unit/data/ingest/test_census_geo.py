"""ZCTA simplification on a one-polygon fixture. No download."""

from __future__ import annotations

import json
from pathlib import Path

from dce.data.ingest.census_geo import simplify_zcta_geojson, write_geojson


def test_simplify_keeps_only_the_zcta_property(tmp_path: Path) -> None:
    source = tmp_path / "one.geojson"
    source.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"ZCTA5CE20": "94402", "ALAND20": 1},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    features = simplify_zcta_geojson(source, zctas=frozenset({"94402"}), tolerance_degrees=0.001)
    assert "crs" not in features
    collection = features["features"]
    assert isinstance(collection, list)
    assert len(collection) == 1
    first = collection[0]
    assert isinstance(first, dict)
    assert first["properties"] == {"zcta": "94402"}
    out = write_geojson(features, tmp_path / "out.geojson")
    assert "94402" in out.read_text(encoding="utf-8")
