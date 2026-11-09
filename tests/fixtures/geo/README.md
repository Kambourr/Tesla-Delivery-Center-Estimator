# Catchment fixtures

`gazetteer_2024_sample.txt` is a header plus eleven rows from the Census
2024 Gazetteer national ZCTA file
(`https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip`).
`INTPTLAT` and `INTPTLONG` are the internal points. Public domain.

The 2025 Bay Area BEV extract that the catchment tests and `estimate` both
read is `data/demo/san_mateo/catchment_bev_2025.csv`. It is every California
ZCTA within 55 straight-line miles of 94402 that has 2025 battery-electric
sales on the CEC ZIP sheet of `New_ZEV_Sales_Last_updated_10-13-2026_ada.xlsx`
(data through 2026-09-30, file index
`https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data`).
`bev_2025` is the sum of `FUEL_TYPE` `Electric` for calendar 2025. The ZIP
sheet has no make. The San Mateo test multiplies by the 9-county Bay Area
2025 Tesla share of Electric sales, 49,704 / 94,131, from that workbook's
County sheet. Centroids are the same Gazetteer internal points.
