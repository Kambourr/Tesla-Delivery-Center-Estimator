# Status

**As of:** 2026-11-09  
**Phase:** M0 bootstrap implemented on `cursor/m0-repo-bootstrap-c1ab`. Pull request: https://github.com/Kambourr/Tesla-Delivery-Center-Estimator/pull/1 — not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done in the open PR (skeleton only; no product logic) |
| M1 SQLite + ZIP stub | Not started |
| M2 Public loaders | Not started |
| M3 Cost/demand model | Not started |
| M4 Scenarios + robustness | Not started |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in M0

- Package `dce` split into ingest, storage, model, scenarios, geo, app, and cli. Stubs are typed. No calculations, no SQLite writes, no network.
- `pyproject.toml` pins the runtime stack and is the config for ruff, mypy, and pytest-cov. Makefile, pre-commit, and CI run lint, typecheck, and tests.
- ADRs 0001–0003, `CONTRIBUTING.md`, `CHANGELOG.md`, `data/seed/README.md`, and a `LICENSE` placeholder (license not chosen).
- CI on `macos-latest` and `ubuntu-latest`. No secrets.

## Not in M0

- Schema, migrations, fixtures, seed rows, loaders, cost math, map HTML, Tkinter window, PyInstaller build.

## Next

M1, after this PR merges. See `docs/AGENT_HANDOFF.md` and `docs/MILESTONES.md`.
