# Bundled seed

This directory is copied into the app so the first launch works offline.
Nationwide ZIP extracts are built by `scripts/build_zip_inputs.py`.
Add files here only when a milestone curates them.

## What belongs here

- CBSA industrial asking rents (`rent_psf_year`, `as_of`, broker, citation URL).
- Frozen ACS rent-model coefficients (income, density, median home value),
  with a note on the GSA Lease Inventory vintage used to calibrate them.
- `zip_crosswalk.csv`: nationwide ZIP to ZCTA, county, and CBSA. Census
  2020 ZCTA-to-county land share, July 2023 CBSA delineation (division code
  when one exists), and the HRSA 2025 ZIP-to-ZCTA workbook for ZIP Codes
  that are not ZCTAs. `resolve_zip` reads this file. HUD's API needs
  `HUD_TOKEN`, which CI does not have, so the shipped crosswalk is not the
  HUD file.
- `zcta_centroid_2024.csv`: Census 2024 Gazetteer internal points and land area.
- `zcta_acs_2024.csv`: ACS 2024 5-year ZCTA population, households, income,
  median gross rent, home value, and vehicles. Mean commute is blank.
- `oews_metro_2025.csv`: May 2025 OEWS wages from the BLS API.
- `zev_zip_sales.csv` and `zev_county_sales.csv`: newest year of the CEC
  New ZEV Sales workbook.
- `coverage.json`: row counts from the build.
- `rent_cbsa.csv` and `rent_model_coeffs.json`: the Kidder Mathews `41884`
  industrial headline and the shipped `acs_rent_v1` exponents.
- A HUD ZIP to CBSA crosswalk large enough for offline demo ZIPs, later a
  national extract if redistribution terms allow it. The live HUD fetch
  remains in `dce.data.ingest.hud_crosswalk` for a machine that has the token.
- Optional San Mateo demo slices that are too small for `data/demo/`.
- `tesla_delivery_centers_2026-11-08.csv`: the Bay Area Tesla delivery
  centers from the 2026-11-08 Find Us list used by the catchment research,
  plus the North San Jose hub (`location_type` `hub`, not on that list).
  `lat`/`lon` are Census 2024 Gazetteer ZCTA internal points for the center
  ZIP. The loader does not fetch tesla.com. The US build script reads it
  and copies its rows unchanged.
- `tesla_delivery_centers_us_2026-11-08.csv`: 123 US Tesla delivery
  locations (120 `delivery`, 1 `hub`, 2 `possible_handover`) in 27 states,
  built by `scripts/build_us_delivery_centers.py` from public sources only.
  Each row carries `source` and `confidence`. `load_us_delivery_centers`
  returns every row; `load_delivery_centers` returns the ten research rows
  the catchment goldens use. Sources, access dates, licences, and
  confidence rules are in `docs/DATA_SOURCES.md` section 10.

The app reads these through `dce.data.rent_defaults.read_rent_seed` and
`dce.storage`. Refresh scripts may update a user database later. They must
not download listing-site HTML into this folder.

## Provenance

| Series | Where it comes from | How it is allowed in |
|---|---|---|
| Industrial asking rent | Public market reports from CBRE, Cushman & Wakefield, Colliers, and JLL | A person types the published headline $/SF and the report URL. No runtime scrape and no PDF dump |
| ZIP to county, CBSA, and ZCTA | Census 2020 ZCTA-county relationship, July 2023 CBSA list 1, HRSA 2025 ZIP-to-ZCTA workbook | US government work. The HUD API remains available when `HUD_TOKEN` is set. It is not the shipped file |
| ZIP adjustment | ACS income, density, and median home value (`B25077`) | US Census Bureau. Public domain |
| Calibration check | GSA Lease Inventory (`Current Annual Rent` / rentable square feet) | GSA open file. Mostly office leases, so it calibrates; it is not industrial truth |
| Weak last resort | HUD Small Area FMR or Zillow ZORI, times a commercial-to-residential ratio | Only the low-confidence tier. Check Zillow research terms before redistributing a derived table |

Census, BLS, HUD, EIA, and GSA products are US government works. Broker
market reports are copyrighted. Store the headline figure and a citation,
not the report. Do not commit LoopNet, Crexi, CoStar, or teardown PDFs.

## Licensing of this folder

The seed is facts plus citations for a student desktop app. That is not a
license to republish the underlying reports. Each row needs `citation` and
`as_of`. If a source's terms forbid redistribution of a derived table, keep
that table out of git and load it into the user database at refresh time
instead.

The repository `LICENSE` file is still a placeholder. Putting a file here
does not make that file open source.
