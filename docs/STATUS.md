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

- Package `dce` with stub modules. Each docstring states that module's contract. No calculations, no SQLite writes, no network.
- `pyproject.toml` pins numpy, pandas, shapely, pyproj, pyogrio, geopandas, folium, and PyYAML. Pytest is the `dev` extra. PyInstaller is the `packaging` extra and is not installed by CI.
- `.gitignore`, `.env.example` (Census, BLS, EIA, HUD only), README quickstart.
- One smoke test: `python -m dce --help` exits 0.
- CI workflow runs install + pytest + CLI help on `macos-latest` and `ubuntu-latest`. No secrets.
- Planning docs aligned to Jacob's 2026-11-09 decisions (Tkinter, macOS `.app`, automatic rent, bundled seed, LLM isolation).

## Not in M0

- Schema, migrations, fixtures, seed rows, loaders, cost math, map HTML, Tkinter window, PyInstaller build.

## Next

M1, after this PR merges. See `docs/AGENT_HANDOFF.md` and `docs/MILESTONES.md`.
