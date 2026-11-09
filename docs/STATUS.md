# Status

**As of:** 2026-11-09
**Phase:** Catchment allocation (delivery centers, CEC ZEV sales, gravity and nearest-center). Pull request [#6](https://github.com/Kambourr/Tesla-Delivery-Center-Estimator/pull/6) is open and not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Done. Merged as #2 (`312d501`) |
| M2 Public loaders | Done. Merged as #4 (`9f8937b`) |
| M3 Cost/demand model | Done. Merged as #3 (`e03407a`) |
| Catchment | Implemented on `cursor/catchment-centers-f980`. Not merged |
| M4 Scenarios + robustness | Not started |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in the catchment work

- `delivery_centers.py` reads `data/seed/tesla_delivery_centers_2026-11-08.csv`. That snapshot is the nine Bay Area delivery centers from the 2026-11-08 research list, plus the North San Jose hub (`location_type` `hub`, not on the Find Us list that day). Coordinates are Census 2024 Gazetteer ZCTA internal points, which are the points the research distances used (Colma is 12.2 miles from 94402). The loader does not fetch tesla.com.
- `zev_sales.py` downloads the CEC New ZEV Sales workbook from `energy.ca.gov` (allowlisted). The ZIP sheet is fuel-only. Tesla deliveries for a California ZIP are Electric sales times Tesla's share of Electric sales on the county sheet, for one calendar year or a trailing run of quarters. `as_of` is the last day of the newest quarter (the 2026-10-13 file is `2026-09-30`). Outside California, `allocate_state_tesla_volume` splits a state Tesla total by `households * (income / 80000) ** 0.3 * (ev_share / 0.03) ** 0.5`. A ZIP missing those inputs is left out.
- `zcta_gazetteer.py` reads Census Gazetteer ZCTA internal points. The national ZIP is on `www2.census.gov`. Tests use `tests/fixtures/geo/gazetteer_2024_sample.txt`.
- `geo/catchment.py` is pure. `catchment_features(geo, centers, demand, beta=2)` returns gravity (base) and nearest-center (low). Drive distance is straight-line miles times 1.25, and pairs beyond 60 miles are out of range. `radius_miles` is used only when no existing centers are passed.
- Schema version 3 adds `delivery_center`, `zcta_centroid`, `zev_sales_zip`, and `zev_sales_county`. Upserts live in `storage/repository.py`. `dce.data.persist` writes the registry `as_of`.
- The San Mateo 94402 fixture (2025 CEC ZIP Electric sales within 55 miles, times the 9-county Tesla share 49,704 / 94,131) reproduces the research nearest-center result: 4,370 deliveries a year, 20 ZCTAs, mean about 6.6 miles, most of it from Colma and Sunnyvale. Gravity at beta 2 with the 60-mile cap is about 5,520, inside the research's "about 5,700".

## Not in this change

- The other 120-odd US delivery centers. The Find Us page is not on the allowlist.
- Rooftop coordinates. A Census geocode of Colma is about 11.6 miles from 94402, not the research 12.2.
- Drive-time routing. The 1.25 circuity factor is the proxy.
- Wiring catchment deliveries into `estimate_annual_deliveries` or the DCF. `src/dce/model/` was left alone.
- A map polygon. M5 still owns Folium.

## Next

M4 or M5, after this pull request merges. The catchment return type is not yet the `GeoDataFrame` named in `docs/MODULE_CONTRACTS.md`. That contract note is in the pull request, not edited here.
