# Status

**As of:** 2026-11-09
**Phase:** Each ZIP uses its own public inputs. `dce precompute` stores the map document. Not merged.

Every figure below is deterministic Python. The estimate, the scenario grid, the tornado, and the precompute do not call an LLM or any other model API. Two runs, including one process and a spawned pool, write the same JSON. `computed_at` is the input vintage `2026-11-09T00:00:00+00:00`, not the clock. Elapsed time is a column and is the only field allowed to change. Stored rows carry `model_version` and `inputs_hash`.

| Milestone | Status |
|---|---|
| M0 Repo bootstrap | Done. Merged as #1 (`8fb16ee`) |
| M1 SQLite + ZIP stub | Done. Merged as #2 (`312d501`) |
| M2 Public loaders | Done. Merged as #4 (`9f8937b`) |
| M3 Cost/demand model | Done. Merged as #3 (`e03407a`) |
| M3.5a Catchment | Done. Merged as #6 (`21b005a`) |
| M3.5b DCF | Done. Merged as #5 (`e2cd901`) |
| Integration (`estimate`) | On main. Now reads each ZIP's local inputs |
| M4 Scenarios + robustness | On main. High horizon is the 10-year lease |
| M5 Map | On main as the pywebview + MapLibre desktop UI (#13) |
| M6 Rent fallback + rates | Rent resolver is wired. Utility rates are still the PG&E B-10 fallback |
| M7 Desktop UI | On main (#13). Folium is not on the path |
| M8 Polish | Not started |

## Done in this integration

- `dce.orchestrator.estimate(zip)` resolves the ZIP, builds the gravity catchment (nearest-center is the low case), feeds the gravity deliveries per year into the cost model, and runs `run_dcf_views`. The default discount rate is Tesla WACC 13.6%. `EstimateResult` carries the catchment (zips, deliveries per year, volume taken from each center), cost per delivery, the top 3 drivers, and both DCF views with NPV, IRR, simple and discounted payback, and the yearly cash-flow table.
- CLI: `dce estimate 94402` prints a text summary. `dce estimate 94402 --json` prints the full result, including both yearly tables.
- ACS `B11001_001E` households are on the loader, schema version 4, and the San Mateo demo cache (94401–94404). The non-California fallback (`non_california_zip_demand`) weights ZIPs by that count. A ZIP with no households is left out. Fixture test, no network.
- Jacob confirmed, and the assumptions file already had: property tax inside NNN rent (`included_in_nnn: true`), expansion rent $1.74 per square foot per month, low-case DCF horizon 8 years.

San Mateo 94402 now uses the nationwide seed. Gravity is 5,565 deliveries a year (nearest 4,469, 21 ZIPs). The wage is the OEWS May 2025 SOC 49-3023 mean for CBSA 41860, $75,730, in place of the $25.91 hourly fallback ($53,893). Rent is the observed Kidder Mathews industrial asking rent for CBSA 41884, $25.68 per square foot per year ($2.14 per square foot per month). Provenance records that source at CBSA 41884 with fallback false. The residential ACS factor is not applied on top of that comp. Demand is 2026 CEC Q1–Q3 battery-electric sales, annualized by 4/3, times the San Mateo Tesla share, times handover 1.10. The 94402 origin itself is about 257 deliveries. The building stays 25,000 square feet. Utilities stay PG&E B-10.

The published research case is the same model at 4,400 deliveries with the old $2.14 rent and the fallback wage: about +$9.7M, 66%, 1.7 years, incremental about −$2.8M.

Previous pipeline, before this change (2025 Bay Area extract, fallback wage, $2.14 rent). Incremental payback did not occur. Simple payback was published for the base case only (1.24 years).

| | Low, H 1.00 | Base, H 1.10 | High, H 1.30 |
|---|---|---|---|
| Gravity (nearest) | 5,280 (3,990) | 5,808 (4,389) | 6,864 (5,187) |
| Cost per delivery | $512 | $489 | $454 |
| Standalone NPV / IRR | +$13.00M / 81.7% | +$15.00M / 90.6% | +$18.98M / 108.1% |
| Discounted payback | 1.59 yr | 1.43 yr | 1.20 yr |
| Incremental NPV | −$2.63M | −$2.61M | −$2.59M |

Same handover cases on the new inputs. Volume scales with the handover factor. Costs do not. Incremental payback still does not occur.

| | Low, H 1.00 | Base, H 1.10 | High, H 1.30 |
|---|---|---|---|
| Gravity (nearest) | 5,059 (4,063) | 5,565 (4,469) | 6,577 (5,281) |
| Cost per delivery | $629 | $605 | $569 |
| Standalone NPV | +$9.65M | +$11.30M | +$14.62M |
| Standalone IRR | 65.9% | 73.5% | 88.1% |
| Simple / discounted payback | 1.66 / 1.96 yr | 1.50 / 1.76 yr | 1.27 / 1.47 yr |
| Incremental NPV | −$3.18M | −$3.22M | −$3.31M |

The outcome low / base / high cards also move wage, rent, fee, WACC, and horizon. Those are what the map and `dce precompute` store. Base matches the handover 1.10 row.

| | Low (bad) | Base | High (good) |
|---|---|---|---|
| Deliveries | 3,373 | 5,565 | 9,500 |
| Cost per delivery | $910 | $605 | $424 |
| Standalone NPV / IRR | −$0.85M / +8.5% | +$11.30M / 73.5% | +$45.28M / 184.2% |
| Simple / discounted payback | 5.84 yr / none | 1.50 / 1.76 yr | 0.60 / 0.66 yr |
| Incremental NPV | −$3.29M | −$3.22M | −$2.85M |

Austin 78701, base. CBSA 12420. Wage $57,440 (OEWS 49-3023, not a fallback). Rent $2.759 per square foot per month from ACS gross rent (fallback, ZCTA 78701). Demand is the national Cox/KBB residual (fallback). Energy $0.2875/kWh and demand $20.50/kW-month are the PG&E B-10 fallback. Gravity 2,512 deliveries a year, nearest 2,574. Cost per delivery $951. Standalone NPV +$0.84M, IRR 18.9%, simple payback 4.89 years, discounted 7.53 years. Incremental NPV −$3.90M, with no IRR and no payback. Top drivers are lease, labor, and capex.

Greenfield, MA 01301 is micropolitan CBSA 24640, so the wage is the national 49-3023 mean $56,420. Amherst 01003 has a suppressed median income and still estimates, using the $80,000 reference. 01093 has no rent of its own. It uses the Franklin County median of ACS gross rent, $1,224 per month, and provenance marks that county rung as a fallback.

1.10 and 1.30 are assumptions. No public source counts used-car handovers. A California county with no CEC Tesla row keeps the 9-county share 49,704 / 94,131. Outside California, `estimate` allocates the 2025 US Tesla total minus the 2025 California Tesla total. It does not invent a per-state total. The 46.2% Cox/KBB EV share remains the fallback inside the demand helper when a caller has EV registrations and no make split.

The published standalone case uses 4,400 deliveries, which is the old nearest-center figure rounded. That reconstruction, at the old rent and the fallback wage, still matches the published +$9.7M / 66% / 1.7 years and incremental about −$2.8M. The live 94402 path does not. The higher OEWS wage moves incremental NPV to about −$3.2M. Top drivers at 94402 are still labor, lease, and straight-line capex.

The M4 low / base / high outcomes keep deliveries as a ratio of each ZIP's own volume, composed with the handover factor (the catchment is already at 1.10). The low case still uses the bad rent, wage, fee, 16.3% WACC, and 8-year horizon. The high horizon is 10 years, the lease.

## Gravity gap on the old fixture (5,523 vs about 5,720)

The geo unit test still locks this fixture: raw BEV times 49,704 / 94,131, nine Bay Area delivery centers. `estimate` does not. It uses the nationwide 2026 seed. The gap below is why that old fixture was not patched to 5,720.

Not a bug in the cap, the centroid, or rounding. The committed fixture reproduces the research radius table (15 miles: 42 ZCTAs, 18,623 BEV, about 9,833 Tesla) and the nearest-center result (4,370 deliveries, 20 ZCTAs, Colma 12.23 straight-line miles). Rounding the Tesla share 49,704 / 94,131 to 0.528 changes gravity by 0.3 deliveries.

The 60-mile drive cap is the ADR-0004 rule. Opening it moves gravity from 5,523 to 5,494, farther from 5,720. A 55-mile straight-line cap gives 5,548. Huff beta 1.5 / 2 / 3 on this fixture is 5,794 / 5,523 / 5,078, each about 150–200 below the research text (5,970 / 5,720 / 5,230).

Nearest-center never sees a far center, so Vallejo, Los Gatos, Corte Madera, and Gilroy do not change the 4,370. Gravity gives each of them a fraction of every in-range ZIP. That fractional share is about 1,150 deliveries here and about 1,350 in the research figure (5,720 − 4,370). Dropping Vallejo alone raises gravity to 5,801, which overshoots 5,720. The research script is not in the repo, so that unpublished filter or distance function cannot be recovered. This code keeps ADR-0004: equal attractiveness, beta 2, straight-line × 1.25, 60-mile cap, all nine delivery centers. The North San Jose hub stays out of the allocation. It is not on the Find Us delivery list in the snapshot; adding it does not change the nearest total and lowers gravity to about 5,167.

## Precompute

Bay Area sample, 4 workers, on this machine: 434 ZIPs in 6.84 seconds (434 ok, 0 error, 63.4 ZIP/s). The seed has 41,034 resolvable ZIPs, so that rate projects a full run of about 10 minutes 47 seconds. After the process exited the database file was 36,134,912 bytes. The CLI reported 45,211,112 bytes, which included the WAL of the still-open reader. Payload JSON was 20,845,754 bytes for those 434 rows. Rent sources: 87 observed industrial (`cbsa_raw`, fallback false), 313 this ZCTA's ACS gross rent, and 34 the county median of ACS gross rent. Both ACS rungs are fallbacks. There were no error rows, so the reason breakdown is empty. A ZIP with no deliveries inside 60 miles, such as 96799, is still stored as an error. `make precompute` runs this sample. The full nation is `dce precompute` with no `--sample`. Model version `2026.11.4-rent-ladder` makes rows from the previous rent formula stale.

## Not in this change

- EIA / OpenEI utility rates. Every ZIP uses PG&E B-10, and the provenance says so.
- A delivery-role wage mix. The stored OEWS series is SOC 49-3023.
- Drive-time routing and rooftop coordinates.
- An LLM. There is no model call on the runtime path.

## Next

A per-ZIP utility rate, and a rent model fit to something broader than the one industrial seed.
