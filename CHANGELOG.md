# Changelog

All notable changes to this project are recorded here.

## Unreleased

### Added

- M0 skeleton for the delivery-center estimator: `src/dce` with ingest,
  storage, model, scenarios, geo, app, and cli layers. Stubs only. No
  calculation and no network calls.
- Tooling in `pyproject.toml`: ruff, mypy, pytest with coverage. Pre-commit
  config, Makefile (`setup`, `lint`, `typecheck`, `test`, `build`), and CI
  that runs lint, typecheck, and tests on macOS and Ubuntu.
- Architecture decision records for Tkinter, macOS packaging, and the rent
  fallback chain.
- `LICENSE` placeholder. A license has not been chosen.
