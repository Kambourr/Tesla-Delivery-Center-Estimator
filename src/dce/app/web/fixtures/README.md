# Bay Area ZCTA fixture

Dev and test stand-in until the national ZCTA shapes land.

- Source: U.S. Census Bureau 2020 Cartographic Boundary File `cb_2020_us_zcta520_500k` (public domain).
- Clip: every ZIP in `data/demo/san_mateo/catchment_bev_2025.csv`, plus the ZIPs on the 2026-11-08 Bay Area delivery-center rows.
- Geometry is simplified to about 80 meters and coordinates are rounded to 5 decimal degrees.
- `properties.zip` is the ZCTA. `properties.lat` and `properties.lon` are Census 2024 Gazetteer internal points when the demand extract has them, otherwise a ring centroid.
- This is not the national file. Point `DCE_ZCTA_GEOJSON` at the real extract when it exists.

`properties.zip` may also be supplied as `ZCTA5CE20`, `ZCTA5CE10`, `GEOID20`, or `GEOID10`. The app normalizes those names.
