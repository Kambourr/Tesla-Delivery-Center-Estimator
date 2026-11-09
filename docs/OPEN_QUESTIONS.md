# Open Questions / Decisions

## Resolved (Jacob, through 2026-11-09)

- **Zero manual input.** Typing a US ZIP resolves rent and every other input. Rent is not a required field. An optional advanced rent override is allowed for a sensitivity check; the default path must not ask for it.
- **Primary platform.** macOS Apple Silicon `.app` via PyInstaller. A Windows EXE is optional and later. CI tests run on `macos-latest` and `ubuntu-latest` with no secrets. The M0 workflow does not build the app.
- **GUI.** A pywebview window hosting a local MapLibre page (ADR-0006). PySide6 and Tkinter are not the UI.
- **Rent automation.** Confirmed. Bundled CBSA industrial asking rents curated from public CBRE / Cushman / Colliers / JLL market reports, with citations. ZIP→CBSA via the HUD crosswalk. Frozen ACS adjustment (income, density, home value) calibrated with the GSA Lease Inventory. Fallback: ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence. Never scrape LoopNet or Crexi. No CoStar, CompStak, Reonomy, ATTOM, Crexi API, or Cherre in v1.
- **Offline.** Bundled SQLite seed so the first launch works offline. Per-source refresh cadence and staleness flags (`fresh` / `aging` / `stale` / `missing`).
- **LLM.** Allowed only inside `dce.extract.pdf_llm`. The model, orchestrator, and GUI calculate path must not call it.
- **Repository.** M0 lands as a pull request into `main`. Do not merge unless Jacob asks.
- **Secrets in the example env.** `.env.example` lists only `CENSUS_API_KEY`, `BLS_API_KEY`, `EIA_API_KEY`, and `HUD_TOKEN`. An OpenEI key and any LLM key stay out of that file until those modules are implemented.
- **Ethics constraint (standing).** Public data only. No Tesla internal data. No LoopNet/Crexi scrape. Broker headline figures appear in the seed only with citations.
- **OEWS join key (M2).** For 94401–94404, HUD ZIP–CBSA division `41884` is still `GeoContext.cbsa`. BLS OEWS for the San Francisco–Oakland metro is stored under parent CBSA `41860` (San Francisco-Oakland-Fremont, CA). `oews_area_for_cbsa` maps `41884` to `41860`.
- **Staleness (M2).** `staleness_status(as_of, ttl_days, today)` is implemented and unit-tested. It is not a column. `missing` means no `as_of`. `fresh` runs through half of `ttl_days`, `aging` through `ttl_days`, and `stale` after that. Eighteen months is 548 days. Broker rent "aging after 2 quarters, stale after 4" is that rule with a 4-quarter TTL.

## Resolved by the revised scope and research (Jacob, 2026-11-08)

- **Scope.** Gravity catchment, `$/delivery` + top 3, scenarios, map, and a 10-year DCF with standalone and incremental views. The default discount rate is Tesla WACC 13.6%. Tesla internal data, home delivery, service repair, and multi-site optimization are out. See PLAN, ADR-0004, and ADR-0005.
- **Catchment** (was 4). Huff gravity model, β = 2, net of existing delivery centers. Radius is a fallback only (ADR-0004).
- **Base annual deliveries** (was 1). 3,000 / 4,500 / 6,500, now a calibration fallback behind the catchment.
- **Staffing and SOCs** (was 2). Minimum 10 FTE, 300 deliveries per FTE, and the delivery-role SOC mix in `labor.wage_mix`. Values are ASSUMPTION build-ups for Jacob to tune.
- **Vehicle mix** (was 3). Model Y 0.70 / Model 3 0.27 / Cybertruck 0.03 / S, X 0.
- **Capex** (was 5). $100 /SF hard fit-out + 20% soft/contingency + $780k equipment, life 10 years (range in the YAML).
- **Property tax vs NNN (Jacob, 2026-11-09).** `property_tax.included_in_nnn: true`. The landlord's property tax stays inside `opex_load`. The property-tax component is 0.
- **Expansion rent (Jacob, 2026-11-09).** `dcf.incremental.status_quo_rent_psf_month` is $1.74 per square foot per month (South San Francisco, Kidder Mathews).
- **Low-case DCF horizon (Jacob, 2026-11-09).** `dcf.horizon_years.low` is 8 years. The base horizon stays 10.
- **High-case DCF horizon (Jacob, 2026-11-09).** `dcf.horizon_years.high` is 10 years, the lease term. The decision scenarios do not assume a renewal past year 10.
- **Demand calibration (Jacob, 2026-11-09).** ZIP demand uses CEC county Tesla totals, then a handover factor of 1.00 / 1.10 / 1.30. Base 1.10 is the default. 1.10 and 1.30 are assumptions. `estimate` competes with the US Find Us delivery list, not the ten Bay Area research rows. Building size stays 25,000 square feet.

## Still open — product / modeling

- **Delivery-center property type for rent** — industrial / flex / auto-service blend weights in the rent model.
- **Incremental lens inputs.** `constraint_share` at Colma/Sunnyvale (0.5 / 0.75 / 1.0) decides the incremental verdict. Also open: whether equipment belongs in the expansion annuity, proximity uplift (0 / 1 / 3%), and whether to include the $250 order fee in the standalone fee.
- **Discount rate.** Corporate WACC 13.6% (default) or a project rate near 9.7%.
- **Horizon and terminal value.** The 8-year low and the 10-year base and high are confirmed (the high case matches the lease). Terminal value is still none by default; renewal is still a toggle.
- **Tax.** California non-conformity (39-year / 7-year straight line, lease-end write-off) needs a tax advisor. A single 27.98% rate is the simpler alternative.
- **Freight.** A per-mile function of factory-to-site distance would generalize the standalone lens beyond the Bay Area.

## Still open — engineering

7. **Offline basemap** — embedded geometry with no tiles, vs a small San Mateo MBTiles file. Polygons must not depend on a live tile server.
8. **API keys** — whether Jacob will supply Census, BLS, HUD, and EIA keys. The rent path is designed to work from the bundled seed with no paid CRE API. M2 keeps CI secret-free with `data/demo/san_mateo`. Live Census refresh needs `CENSUS_API_KEY`. BLS works for the small OEWS query without a key. The DMV ZIP query needs no key.
9. **LLM PDF extract** — ship the optional module vs manual parsers only for utility PDFs.
10. **Deadline** — practicum / portfolio date.
11. **Windows EXE** — whether to schedule it after the macOS `.app`. Not part of M0–M7 acceptance.
12. **Scenario id on `EstimateResult`.** `driver_rank_stability` takes a `baseline_id`, and the data dictionary lists `scenario_id`, but the dataclass in `MODULE_CONTRACTS.md` has no id field. Add it when M4 implements scenarios.
13. **License.** `LICENSE` is a placeholder and grants nothing. Choose MIT, Apache-2.0, or another license, or leave the repo private with all rights reserved. Do not fill in license text until then.

## Parked after M2 (out of scope until a later milestone)

14. **HUD CBSA column vs parent metro.** Resolved in M2. See the resolved list above. `GeoContext.cbsa` remains the HUD division code.
15. **Staleness is computed, not stored.** Resolved in M2. See the resolved list above. Do not add a status column.
16. **Quarterly HUD address ratios.** The M1 fixture sets `tot_ratio` to 1 because these four ZIPs sit entirely in county `06081` and division `41884`. It is not a copy of a quarterly HUD address-count file (the download sits behind a WAF, and the API needs `HUD_TOKEN`). A refresh can replace the ratios later. `fetch_zip_crosswalk` stays a stub.
17. **Where the crosswalk lives at runtime.** `resolve_zip` reads `tests/fixtures/hud_9440x.json` from the checkout. Copying a crosswalk into `data/seed/` and into the user database, and resolving from those rows, waits for the seed and packaging milestones. `zip_tract` is not in the M1 schema.
18. **Migration shape after version 1.** M1 applies `CREATE TABLE IF NOT EXISTS` and inserts `schema_migrations.version = 1`. A later column change needs a new version and an `ALTER` or rebuild. Leave the version-1 statements in place once a user database exists.
19. **Still later:** first-launch seed copy, physical rent tables (`rent_cbsa`, `rent_zip_obs`, `rent_model_coeffs`, `rent_resolved_cache`), `resolve_rent`, and the macOS `.app` build on a Mac. The map window is ADR-0006, not Tkinter or Folium. M2 added the ACS, OEWS, and DMV loaders only. QCEW, HUD download, TIGER, EIA, OpenEI, and the CEC bulk workbook stay stubs. Windows path lookup exists; a Windows EXE remains optional.
