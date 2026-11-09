# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Added

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
