# ZCTA boundaries

`zcta_bay_area.geojson` is the committed fixture. It holds the ZCTAs whose
dominant county, from `data/seed/zip_crosswalk.csv`, is one of the nine Bay
Area counties (Alameda, Contra Costa, Marin, Napa, San Francisco, San Mateo,
Santa Clara, Solano, Sonoma). The only property is `zcta`. Coordinates are
EPSG:4326.

`zcta_us.pmtiles` is the nationwide MapLibre asset. It is gitignored.
`make zcta-boundaries` rebuilds both from the Census 2020 cartographic ZCTA
file (`cb_2020_us_zcta520_500k.zip`). Polygons are Douglas-Peucker simplified
by 0.001 degrees (about 111 meters) with topology preserved. The PMTiles
archive is vector tiles, layer `zcta`, zooms 3 through 8, and it keeps every
polygon. MapLibre draws that faster than one national GeoJSON, because only
the tiles in view are decoded.

`boundary_build.json` records the byte sizes from the last build. Sources
and the access date are in `docs/DATA_SOURCES.md` section 11. The click API
is `docs/contracts/zip_data.md`.
