# Status

**As of:** 2026-11-09
**Phase:** M2 public loaders (Census ACS, BLS OEWS, California DMV). Pull request not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Done. Merged as #2 (`312d501`) |
| M2 Public loaders | Implemented on `cursor/m2-public-loaders-c599`. Pull request not merged |
| M3 Cost/demand model | Not started |
| M4 Scenarios + robustness | Not started |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in M2

- `census_acs.py` fetches ACS 5-year population (`B01003_001E`), median household income (`B19013_001E`), aggregate vehicles (`B25046_001E`), median home value (`B25077_001E`), and mean commute (`S0801_C01_046E`) from `api.census.gov`. The request needs `CENSUS_API_KEY`. The key is not written to `source_registry`.
- `bls_oews.py` fetches the annual mean and median for one metro × SOC from `api.bls.gov`. SOC `49-3023` in CBSA `41860` (San Francisco-Oakland-Fremont, CA) is the San Mateo wage. May 2025 mean is $75,730 and median is $76,030. `BLS_API_KEY` is optional.
- `ca_ev.py` reads light-duty DMV fuel counts for one ZIP from `data.ca.gov` (no key). Battery Electric, Plug-in Hybrid, and Hydrogen Fuel Cell map to `bev`, `phev`, and `fcev`. For 94402 on `2024-12-31` those are 2,257 / 561 / 4, and `total_ldv` is 21,403.
- Ingest still does not open SQLite. `dce.data.persist` upserts the fact rows and a `source_registry` `as_of`. ACS `as_of` is 31 December of the vintage year. OEWS `as_of` is 1 May of the survey year. DMV `as_of` is the file's `Date` column.
- `scripts/fetch_demo_cache.py` loads `data/demo/san_mateo` with no API keys and no network. `scripts/check_staleness.py` prints `fresh` / `aging` / `stale` / `missing`. `scripts/refresh_public_data.py` is the live refresh.
- `staleness_status` is unit-tested. `missing` means no `as_of`. `fresh` is the first half of `ttl_days`, `aging` is the rest of the TTL, and `stale` is older than the TTL. Eighteen months is 548 days. Status is not a column.
- HUD division `41884` stays on `GeoContext.cbsa`. OEWS wages for that division are stored under parent CBSA `41860`. `oews_area_for_cbsa` does the mapping.
- Schema version 2 adds `zcta_acs.median_home_value`. Version 1 SQL is unchanged. `2000001` is the Census top-code for $2,000,000+.

On 2026-11-09 the committed vintages are stale under the 18-month rule (ACS and DMV `as_of` 2024-12-31, OEWS `as_of` 2025-05-01). They are still the latest public vintages this milestone captured. The badge is honest about age; it does not mean the fetch failed.

## Not in M2

- CEC bulk workbook on `energy.ca.gov`. The DMV ZIP query is the no-key accept path. A spreadsheet parser can wait until a milestone needs the CEC file itself.
- QCEW, HUD download, TIGER, EIA, OpenEI, and the other ingest stubs.
- First-launch copy of a bundled seed database, `resolve_rent`, cost math, scenarios, Folium, Tkinter, and PyInstaller.
- A stored staleness column. Call `staleness_status`.

## Next

M3, after this pull request merges. See `docs/MILESTONES.md` and `docs/AGENT_HANDOFF.md`.
