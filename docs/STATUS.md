# Status

**As of:** 2026-11-09
**Phase:** M1 SQLite schema, config paths, and local ZIP resolution. Pull request not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Implemented on `cursor/m1-sqlite-zip-resolve-f2f9`. Not merged |
| M2 Public loaders | Not started |
| M3 Cost/demand model | Not started |
| M4 Scenarios + robustness | Not started |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in M1

- `storage/schema.sql` and `storage/migrate.py` create the data-dictionary tables plus `zip_county`, `zip_cbsa`, and `zip_zcta`. Creating the database is idempotent. `schema_migrations` records version 1.
- `source_registry` stores `as_of`, `fetched_at`, `ttl_days`, and `bytes`. `upsert_source` / `get_source` round-trip a row. Staleness status stays computed later; it is not a column.
- `config.py` resolves the ADR-0002 directories: macOS `~/Library/Application Support/DeliveryCenterEstimator`, Windows `%LOCALAPPDATA%\DeliveryCenterEstimator`, Linux `~/.local/share/delivery-center-estimator`. Looking up a path does not create it.
- `geo/resolve.py` reads `tests/fixtures/hud_9440x.json`. `resolve_zip("94402")` returns county `06081` and CBSA `41884` (the HUD ZIP–CBSA code on that row). An unknown ZIP raises `UnknownZipError`. No network and no SQLite in geo or model.

## Not in M1

- Network loaders, `staleness_status`, bundled-seed copy on first launch, physical rent tables, `resolve_rent`, cost math, Folium HTML, Tkinter window, PyInstaller.
- A quarterly HUD address-ratio download. The fixture is a four-ZIP slice.

## Next

M2, after this pull request merges. See `docs/MILESTONES.md` and `docs/AGENT_HANDOFF.md`.
