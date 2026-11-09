# Open Questions / Decisions

## Resolved (Jacob, through 2026-11-09)

- **Zero manual input.** Typing a US ZIP resolves rent and every other input. Rent is not a required field. An optional advanced rent override is allowed for a sensitivity check; the default path must not ask for it.
- **Primary platform.** macOS Apple Silicon `.app` via PyInstaller. A Windows EXE is optional and later. CI tests run on `macos-latest` and `ubuntu-latest` with no secrets. The M0 workflow does not build the app.
- **GUI.** Tkinter. The Folium map opens in the system browser. PySide6 is not v1 and is not an open implementation choice unless Jacob reopens it.
- **Rent automation.** Confirmed. Bundled CBSA industrial asking rents curated from public CBRE / Cushman / Colliers / JLL market reports, with citations. ZIP→CBSA via the HUD crosswalk. Frozen ACS adjustment (income, density, home value) calibrated with the GSA Lease Inventory. Fallback: ZIP-adjusted CBSA → county → CBSA → state → national → HUD SAFMR/ZORI proxy flagged low-confidence. Never scrape LoopNet or Crexi. No CoStar, CompStak, Reonomy, ATTOM, Crexi API, or Cherre in v1.
- **Offline.** Bundled SQLite seed so the first launch works offline. Per-source refresh cadence and staleness flags (`fresh` / `aging` / `stale` / `missing`).
- **LLM.** Allowed only inside `dce.extract.pdf_llm`. The model, orchestrator, and GUI calculate path must not call it.
- **Repository.** M0 lands as a pull request into `main`. Do not merge unless Jacob asks.
- **Secrets in the example env.** `.env.example` lists only `CENSUS_API_KEY`, `BLS_API_KEY`, `EIA_API_KEY`, and `HUD_TOKEN`. An OpenEI key and any LLM key stay out of that file until those modules are implemented.
- **Ethics constraint (standing).** Public data only. No Tesla internal data. No LoopNet/Crexi scrape. Broker headline figures appear in the seed only with citations.

## Still open — product / modeling

1. **Base annual deliveries** at a “median” demand score (placeholder 2,500).
2. **Staffing curve** — headcount vs deliveries; SOCs beyond 49-3023.
3. **Vehicle mix defaults** for the demo.
4. **Catchment** — fixed miles vs neighbor ZCTAs.
5. **Capex $/SF and life** — still auto-defaulted (not user-typed); confirm the placeholder band ($80–$150 /SF, 10 years).
6. **Delivery-center property type for rent** — industrial / flex / auto-service blend weights in the rent model.

## Still open — engineering

7. **Offline basemap** — embedded geometry with no tiles, vs a small San Mateo MBTiles file. Polygons must not depend on a live tile server.
8. **API keys** — whether Jacob will supply Census, BLS, HUD, and EIA keys. The rent path is designed to work from the bundled seed with no paid CRE API. Loaders must have fixture tests so CI stays secret-free.
9. **LLM PDF extract** — ship the optional module vs manual parsers only for utility PDFs.
10. **Deadline** — practicum / portfolio date.
11. **Windows EXE** — whether to schedule it after the macOS `.app`. Not part of M0–M7 acceptance.
12. **Scenario id on `EstimateResult`.** `driver_rank_stability` takes a `baseline_id`, and the data dictionary lists `scenario_id`, but the dataclass in `MODULE_CONTRACTS.md` has no id field. Add it when M4 implements scenarios.
13. **License.** `LICENSE` is a placeholder and grants nothing. Choose MIT, Apache-2.0, or another license, or leave the repo private with all rights reserved. Do not fill in license text until then.
