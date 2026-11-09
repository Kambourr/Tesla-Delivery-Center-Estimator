# Status

**As of:** 2026-11-09
**Phase:** Integration. `estimate(zip)` runs the calibrated catchment, cost, and both DCF views. Not merged.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Done. Merged as #2 (`312d501`) |
| M2 Public loaders | Done. Merged as #4 (`9f8937b`) |
| M3 Cost/demand model | Done. Merged as #3 (`e03407a`) |
| M3.5a Catchment | Done. Merged as #6 (`21b005a`) |
| M3.5b DCF | Done. Merged as #5 (`e2cd901`) |
| Integration (`estimate`) | Implemented on this branch. Not merged |
| M4 Scenarios + robustness | Implemented. High horizon is the 10-year lease. Not merged |
| M5 Map | Not started |
| M6 Rent fallback + rates | Not started |
| M7 Tkinter GUI + macOS .app | Not started |
| M8 Polish | Not started |

## Done in this integration

- `dce.orchestrator.estimate(zip)` resolves the ZIP, builds the gravity catchment (nearest-center is the low case), feeds the gravity deliveries per year into the cost model, and runs `run_dcf_views`. The default discount rate is Tesla WACC 13.6%. `EstimateResult` carries the catchment (zips, deliveries per year, volume taken from each center), cost per delivery, the top 3 drivers, and both DCF views with NPV, IRR, simple and discounted payback, and the yearly cash-flow table.
- CLI: `dce estimate 94402` prints a text summary. `dce estimate 94402 --json` prints the full result, including both yearly tables.
- ACS `B11001_001E` households are on the loader, schema version 4, and the San Mateo demo cache (94401–94404). The non-California fallback (`non_california_zip_demand`) weights ZIPs by that count. A ZIP with no households is left out. Fixture test, no network.
- Jacob confirmed, and the assumptions file already had: property tax inside NNN rent (`included_in_nnn: true`), expansion rent $1.74 per square foot per month, low-case DCF horizon 8 years.

San Mateo 94402, fixtures only. Demand is the CEC county Tesla anchor times the base handover factor 1.10, allocated against the US Find Us delivery list (120 `delivery` rows; the hub and possible-handover rows stay out). Gravity volume is 5,808 deliveries a year. The building stays 25,000 square feet.

| | Research case at 4,400 | This pipeline at 5,808 |
|---|---|---|
| Cost per delivery | $562 | $489 |
| Standalone NPV @13.6% | +$9.68M (published +$9.7M) | +$15.00M |
| Standalone IRR | 66.3% (published 66%) | 90.6% |
| Simple / discounted payback | 1.66 / 1.97 yr (published 1.7 / 2.0) | 1.24 / 1.43 yr |
| Incremental NPV | −$2.65M (published −$2.8M) | −$2.61M |

Handover cases on the same path (county anchor, US delivery list, base costs). Colma is gravity volume before the candidate and after it. Incremental discounted payback does not occur.

| | Low, H 1.00 | Base, H 1.10 | High, H 1.30 |
|---|---|---|---|
| San Mateo gravity (nearest) | 5,280 (3,990) | 5,808 (4,389) | 6,864 (5,187) |
| Colma before → after | 7,326 → 5,816 | 8,059 → 6,397 | 9,524 → 7,560 |
| Cost per delivery | $512 | $489 | $454 |
| Standalone NPV / IRR | +$13.00M / 81.7% | +$15.00M / 90.6% | +$18.98M / 108.1% |
| Discounted payback | 1.59 yr | 1.43 yr | 1.20 yr |
| Incremental NPV | −$2.63M | −$2.61M | −$2.59M |

1.10 and 1.30 are assumptions. No public source counts used-car handovers. A California county with no CEC Tesla row keeps the 9-county share 49,704 / 94,131. A non-California ZIP with EV registrations and no Tesla make split uses the Cox/KBB 2025 share, 46.2%.

The published standalone case uses 4,400 deliveries, which is the old nearest-center figure rounded. This pipeline feeds calibrated gravity, so standalone NPV, IRR, and payback move. Incremental NPV stays inside −$2.8M ± $0.25M because that lens scales the avoided cost with the same volume. Top drivers are labor, lease, and straight-line capex. The research prose band of about $590–$660 per delivery is the rough range around the 4,400-delivery case; the model that matches the research cash-flow table to $1k produces $562 there and $489 at 5,808.

The M4 low / base / high outcomes keep deliveries as a ratio of each ZIP's own volume, composed with the handover factor (the catchment is already at 1.10). The low case still uses the bad rent, wage, fee, 16.3% WACC, and 8-year horizon. The high horizon is 10 years, the lease.

## Gravity gap on the old fixture (5,523 vs about 5,720)

The geo unit test still locks this fixture: raw BEV times 49,704 / 94,131, nine Bay Area delivery centers. `estimate` does not. It uses the county anchor, handover 1.10, and the US delivery list, which is the 5,808 row above. The gap below is why that old fixture was not patched to 5,720.

Not a bug in the cap, the centroid, or rounding. The committed fixture reproduces the research radius table (15 miles: 42 ZCTAs, 18,623 BEV, about 9,833 Tesla) and the nearest-center result (4,370 deliveries, 20 ZCTAs, Colma 12.23 straight-line miles). Rounding the Tesla share 49,704 / 94,131 to 0.528 changes gravity by 0.3 deliveries.

The 60-mile drive cap is the ADR-0004 rule. Opening it moves gravity from 5,523 to 5,494, farther from 5,720. A 55-mile straight-line cap gives 5,548. Huff beta 1.5 / 2 / 3 on this fixture is 5,794 / 5,523 / 5,078, each about 150–200 below the research text (5,970 / 5,720 / 5,230).

Nearest-center never sees a far center, so Vallejo, Los Gatos, Corte Madera, and Gilroy do not change the 4,370. Gravity gives each of them a fraction of every in-range ZIP. That fractional share is about 1,150 deliveries here and about 1,350 in the research figure (5,720 − 4,370). Dropping Vallejo alone raises gravity to 5,801, which overshoots 5,720. The research script is not in the repo, so that unpublished filter or distance function cannot be recovered. This code keeps ADR-0004: equal attractiveness, beta 2, straight-line × 1.25, 60-mile cap, all nine delivery centers. The North San Jose hub stays out of the allocation. It is not on the Find Us delivery list in the snapshot; adding it does not change the nearest total and lowers gravity to about 5,167.

## Not in this change

- `resolve_rent` and the EIA / OpenEI loaders. San Mateo rent ($2.14 /sf/month, Kidder Mathews) and PG&E B-10 rates ($0.2875 /kWh, $20.50 /kW-month) come from `data/demo/san_mateo/operating_inputs.json`. The wage is `labor.fallback_wage_hourly` because the demo OEWS row is SOC 49-3023, not the delivery-role mix.
- A non-California `estimate(zip)`. ZIP resolution still knows only 94401–94404. The household allocator is implemented and tested; `estimate` calls it only when the state is not California and a state Tesla total is passed in.
- The map. `map_path` is `None`. M5 still owns Folium.
- Drive-time routing and rooftop coordinates.

## Next

M4 (scenario grid, including DCF shocks) or M6 (rent fallback and rates), so `estimate` stops reading the San Mateo operating-input file. M5 still owns the map.
