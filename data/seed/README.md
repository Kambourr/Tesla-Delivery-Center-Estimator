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
- `construction_cost_factor.csv`: DoD UFS 3-701-01 (6 June 2026) Table 4-1
  CONUS MILCON construction area cost factors, 1.00 = DoD 96-base-city
  average. County (lower median of DoD sites), CBSA and state (lower median
  of county rows), and national rows. This is the fit-out index.
- `bea_rpp_2024.csv`: BEA 2024 goods and all-items regional price parities.
  Fit-out fallback only, when the DoD table has no county, CBSA, or state.
- `electricity_commercial.csv` and `county_utility.csv`: commercial
  electricity. Utility tariff, then EIA-861 utility average, then EIA
  Table 5.6.A state, then the U.S. total. PG&E B-10 is the tariff row for
  utility `14328`.
- `property_tax_commercial.csv`: Lincoln Institute / MCFE commercial
  (Tables 3a–3c, not homestead) effective rates, taxes paid in 2024.
  `effective_rate` is per dollar of land and building (the $1 million bill
  over $1 million where fixtures are exempt); `commercial_rate` is the
  published rate; `industrial_rate` (Tables 4a, 4c, 4e) is for reference.
  County, then a studied large city in the same CBSA and state, then state
  rural or state urban, then the 53-city mean.
- `zev_zip_sales.csv` and `zev_county_sales.csv`: newest year of the CEC
  New ZEV Sales workbook.
- `coverage.json`: row counts from the build.
- `rent_cbsa.csv` and `rent_model_coeffs.json`: the Kidder Mathews `41884`
  industrial headline and the shipped `acs_rent_v1` exponents.
- `rent_market.csv`: broker market-report asking rents for 29 CBSAs or
  metro divisions and 21 counties (NYC boroughs, Long Island, North and
  Central New Jersey), all Cushman & Wakefield MarketBeat Q3 2026. Columns:
  `geography_level` (`county` or `cbsa`), `geography_id`, `market`,
  `submarket`, `property_type` (`industrial_flex`, `industrial_overall`, or
  `office_showroom_proxy`), `rent_psf_year` (annual NNN), `reported_rent`,
  `reported_unit` (`usd_psf_year` or `usd_psf_month`), `reported_basis`
  (`nnn` or `full_service_gross`), `source`, `report`, `quarter`, `as_of`,
  `url`, `note`. `rent_psf_year` = reported × 12 when monthly, ÷ 1.15 when
  full-service gross; the reader rejects a row that does not match. The flex
  column is used where the report publishes one for that geography,
  otherwise the overall industrial rent. Manhattan uses the office overall
  asking rent as a showroom proxy because the reports track no Manhattan
  industrial stock. Rules and coverage: `docs/DATA_SOURCES.md` §8.
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
| Industrial asking rent | Public market reports from CBRE, Cushman & Wakefield, Colliers, JLL, Newmark, and Kidder Mathews (`rent_cbsa.csv`, `rent_market.csv`) | A person types the published headline $/SF, its unit and basis, and the report URL. No runtime scrape and no PDF dump |
| ZIP to county, CBSA, and ZCTA | Census 2020 ZCTA-county relationship, July 2023 CBSA list 1, HRSA 2025 ZIP-to-ZCTA workbook | US government work. The HUD API remains available when `HUD_TOKEN` is set. It is not the shipped file |
| ZIP adjustment | ACS income, density, and median home value (`B25077`) | US Census Bureau. Public domain |
| Calibration check | GSA Lease Inventory (`Current Annual Rent` / rentable square feet) | GSA open file. Mostly office leases, so it calibrates; it is not industrial truth |
| Commercial property tax | Lincoln Institute / MCFE 50-State study, taxes paid in 2024 | Rates parsed from the study tables, with a citation. The PDF is not stored |
| Construction cost factor | DoD UFS 3-701-01 (6 June 2026), Table 4-1 CONUS | US government work, approved for public release. Fit-out index |
| Goods price parity | BEA Regional Price Parities, 2024 | US government work. Fit-out fallback only |
| Commercial electricity | EIA-861, EIA Electric Power Monthly Table 5.6.A, PG&E Schedule B-10 | US government work, plus the published tariff. No runtime download |

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
