# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Added

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
