# Status

**As of:** 2026-11-09
**Phase:** Integration. `estimate(zip)` runs catchment, cost, and both DCF views. Not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Done. Merged as #2 (`312d501`) |
| M2 Public loaders | Done. Merged as #4 (`9f8937b`) |
| M3 Cost/demand model | Done. Merged as #3 (`e03407a`) |
| M3.5a Catchment | Done. Merged as #6 (`21b005a`) |
| M3.5b DCF | Done. Merged as #5 (`e2cd901`) |
| Integration (`estimate`) | Implemented on this branch. Not merged |
| M4 Scenarios + robustness | Not started |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in this integration

- `dce.orchestrator.estimate(zip)` resolves the ZIP, builds the gravity catchment (nearest-center is the low case), feeds the gravity deliveries per year into the cost model, and runs `run_dcf_views`. The default discount rate is Tesla WACC 13.6%. `EstimateResult` carries the catchment (zips, deliveries per year, volume taken from each center), cost per delivery, the top 3 drivers, and both DCF views with NPV, IRR, simple and discounted payback, and the yearly cash-flow table.
- CLI: `dce estimate 94402` prints a text summary. `dce estimate 94402 --json` prints the full result, including both yearly tables.
- ACS `B11001_001E` households are on the loader, schema version 4, and the San Mateo demo cache (94401–94404). The non-California fallback (`non_california_zip_demand`) weights ZIPs by that count. A ZIP with no households is left out. Fixture test, no network.
- Jacob confirmed, and the assumptions file already had: property tax inside NNN rent (`included_in_nnn: true`), expansion rent $1.74 per square foot per month, low-case DCF horizon 8 years.

San Mateo 94402, fixtures only, gravity volume 5,523 deliveries a year:

| | Research case at 4,400 | This pipeline at 5,523 |
|---|---|---|
| Cost per delivery | $562 | $501 |
| Standalone NPV @13.6% | +$9.68M (published +$9.7M) | +$13.92M |
| Standalone IRR | 66.3% (published 66%) | 85.8% |
| Simple / discounted payback | 1.66 / 1.97 yr (published 1.7 / 2.0) | 1.31 / 1.51 yr |
| Incremental NPV | −$2.65M (published −$2.8M) | −$2.62M |

The published standalone case uses 4,400 deliveries, which is the nearest-center figure rounded. This pipeline feeds gravity, so standalone NPV, IRR, and payback move. Incremental NPV stays inside −$2.8M ± $0.25M because that lens scales the avoided cost with the same volume. Top drivers are labor, lease, and straight-line capex. The research prose band of about $590–$660 per delivery is the rough range around the 4,400-delivery case; the model that matches the research cash-flow table to $1k produces $562 there and $501 at 5,523.

## Gravity gap (5,523 vs about 5,720)

Not a bug in the cap, the centroid, or rounding. The committed fixture reproduces the research radius table (15 miles: 42 ZCTAs, 18,623 BEV, about 9,833 Tesla) and the nearest-center result (4,370 deliveries, 20 ZCTAs, Colma 12.23 straight-line miles). Rounding the Tesla share 49,704 / 94,131 to 0.528 changes gravity by 0.3 deliveries.

The 60-mile drive cap is the ADR-0004 rule. Opening it moves gravity from 5,523 to 5,494, farther from 5,720. A 55-mile straight-line cap gives 5,548. Huff beta 1.5 / 2 / 3 on this fixture is 5,794 / 5,523 / 5,078, each about 150–200 below the research text (5,970 / 5,720 / 5,230).

Nearest-center never sees a far center, so Vallejo, Los Gatos, Corte Madera, and Gilroy do not change the 4,370. Gravity gives each of them a fraction of every in-range ZIP. That fractional share is about 1,150 deliveries here and about 1,350 in the research figure (5,720 − 4,370). Dropping Vallejo alone raises gravity to 5,801, which overshoots 5,720. The research script is not in the repo, so that unpublished filter or distance function cannot be recovered. This code keeps ADR-0004: equal attractiveness, beta 2, straight-line × 1.25, 60-mile cap, all nine delivery centers. The North San Jose hub stays out of the allocation. It is not on the Find Us delivery list in the snapshot; adding it does not change the nearest total and lowers gravity to about 5,167.

## Not in this change

- The national delivery-center list. Another change owns `data/seed/` and `delivery_centers.py`.
- `resolve_rent` and the EIA / OpenEI loaders. San Mateo rent ($2.14 /sf/month, Kidder Mathews) and PG&E B-10 rates ($0.2875 /kWh, $20.50 /kW-month) come from `data/demo/san_mateo/operating_inputs.json`. The wage is `labor.fallback_wage_hourly` because the demo OEWS row is SOC 49-3023, not the delivery-role mix.
- A non-California `estimate(zip)`. ZIP resolution still knows only 94401–94404. The household allocator is implemented and tested; `estimate` calls it only when the state is not California and a state Tesla total is passed in.
- The map. `map_path` is `None`. M5 still owns Folium.
- Drive-time routing and rooftop coordinates.

## Next

M4 (scenario grid, including DCF shocks) or M6 (rent fallback and rates), so `estimate` stops reading the San Mateo operating-input file. M5 still owns the map.
