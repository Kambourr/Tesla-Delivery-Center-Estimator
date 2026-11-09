# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Added

- County Tesla calibration and a handover factor. California ZIP demand is
  BEV times that county's 2025 CEC Tesla total (49,704 / 94,131 only where
  the extract has no CEC row), then times 1.00 / 1.10 / 1.30. Base 1.10 is
  the default. 1.10 and 1.30 are assumptions: no public count of used-car
  handovers. Outside California, EV registrations with no make split use
  the Cox/KBB 2025 Tesla share of US EV sales, 46.2%.
- `estimate(zip)` competes with the US Find Us delivery list (120
  `delivery` rows). The hub and possible-handover rows stay out. San Mateo
  94402 at the base handover factor is 5,808 gravity deliveries a year and
  4,389 nearest-center. Cost per delivery is about $489. Standalone NPV is
  about +$15.0M, IRR about 91%, discounted payback about 1.4 years.
  Incremental NPV is about −$2.6M. The building stays 25,000 square feet.
- The M4 high scenario horizon is 10 years, the lease term, not 15. Low and
  high deliveries stay a ratio of each ZIP's own volume, composed with the
  handover factor. The low case keeps its 8-year horizon and its other bad
  shocks.
- `estimate(zip)` runs the whole pipeline with no manual input: ZIP resolution,
  gravity catchment (nearest-center is the low case), cost per delivery with
  the top 3 drivers, and both DCF views (standalone delivery-fee is the
  headline, incremental-to-Tesla is the check) at Tesla WACC 13.6%. The CLI
  is `dce estimate 94402`, with `--json` for the full cash-flow tables.
  Before the county anchor and the US center list, San Mateo gravity was
  5,523 deliveries a year (standalone NPV about +$13.9M). The calibrated
  figures are in the bullets above. The published +$9.7M / 66% / 1.7 years
  is the same model at the research case of 4,400 deliveries.
- ACS household counts (`B11001_001E`) on the Census loader, schema version
  4, and the San Mateo demo cache, so the non-California demand fallback
  can weight ZIPs. A ZIP with no households is skipped.
- The San Mateo gravity gap is documented, not patched. 5,523 versus the
  research text's about 5,720 is not the 60-mile cap, the Gazetteer
  centroid, or rounding. Nearest-center still matches 4,370. See
  `docs/STATUS.md`.
- Catchment allocation. A candidate ZIP competes with existing Tesla delivery
  centers instead of taking every ZIP inside a fixed radius. Drive distance
  is straight-line miles times 1.25, capped at 60 miles. The base case is
  Huff gravity with beta 2. The low case is the nearest center. For San
  Mateo 94402 the fixture reproduces about 4,370 nearest-center deliveries
  a year over 20 ZCTAs (mostly from Colma and Sunnyvale) and about 5,520
  gravity deliveries, inside the research band of about 4,400 to 5,700.
- A committed 2026-11-08 snapshot of the Bay Area Tesla delivery centers
  (plus the North San Jose hub) in `data/seed/`, with storage upserts.
  Coordinates are Census 2024 ZCTA internal points. The loader does not
  call tesla.com.
- A California Energy Commission New ZEV Sales loader on `energy.ca.gov`.
  ZIP rows are fuel counts. Tesla's make share comes from the county sheet.
  Outside California, state Tesla volume is split across ZIPs by households,
  income, and EV share using the existing demand elasticities. A ZIP with
  no data is skipped.
- Census Gazetteer ZCTA centroids, schema version 3 (`delivery_center`,
  `zcta_centroid`, `zev_sales_zip`, `zev_sales_county`).
- M2 public loaders for Census ACS 5-year ZCTA facts, BLS OEWS metro wages
  (SOC 49-3023), and California DMV light-duty fuel counts by ZIP. Fetch stays
  on `api.census.gov`, `api.bls.gov`, and `data.ca.gov`. SQL upsert and
  `source_registry.as_of` stay in storage. The San Mateo demo
  (`scripts/fetch_demo_cache.py`, `data/demo/san_mateo`) loads 94401–94404
  without API keys. Census refresh needs `CENSUS_API_KEY`.
- Staleness classification (`fresh` / `aging` / `stale` / `missing`) from
  `as_of` and `ttl_days`. Eighteen months is 548 days. Aging is the second
  half of the TTL. `scripts/check_staleness.py` prints one line per source.
- OEWS join key for the San Mateo ZIPs: HUD division `41884` maps to parent
  CBSA `41860` (San Francisco-Oakland-Fremont, CA). `GeoContext.cbsa` is
  unchanged.
- Schema version 2 adds `zcta_acs.median_home_value` (ACS `B25077_001E`).
- M1 SQLite schema and idempotent migrations for the data-dictionary tables
  (`source_registry`, `zcta_acs`, `oews_wage`, `ev_zip`, `utility_rate`,
  `rent_default`, `extract_cache`) and the ZIP geography tables
  (`zip_county`, `zip_cbsa`, `zip_zcta`). `source_registry` stores `as_of`,
  `fetched_at`, and `ttl_days`.
- OS application-data paths for the user database: macOS Application Support,
  Windows `LOCALAPPDATA`, and the Linux `~/.local/share` directory from
  ADR-0002.
- Local HUD ZIP crosswalk fixture for 94401–94404 and `resolve_zip`. Resolving
  94402 returns San Mateo County `06081` and CBSA `41884`. An unknown ZIP
  raises `UnknownZipError`. No network.
- M0 skeleton for the delivery-center estimator: `src/dce` with ingest,
  storage, model, scenarios, geo, app, and cli layers. Stubs only. No
  calculation and no network calls.
- Tooling in `pyproject.toml`: ruff, mypy, pytest with coverage. Pre-commit
  config, Makefile (`setup`, `lint`, `typecheck`, `test`, `build`), and CI
  that runs lint, typecheck, and tests on macOS and Ubuntu.
- Architecture decision records for Tkinter, macOS packaging, and the rent
  fallback chain.
- `LICENSE` placeholder. A license has not been chosen.
