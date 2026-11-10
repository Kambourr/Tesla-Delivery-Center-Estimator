# Public Data Sources

All sources below were URL-checked as of 2026-11-08 (America/Los_Angeles). **PUBLIC DATA ONLY.**

## Licensing & scraping risk matrix

| Source | License / terms | Scrape? | App strategy |
|---|---|---|---|
| Census ACS / TIGER | Public domain (US Gov) | API / bulk OK | Cache in SQLite |
| BLS OEWS / QCEW | Public domain (US Gov) | Bulk / API OK | Cache |
| HUD-USPS crosswalk | Free HUD User account + API token | API OK | Cache; store token in local `.env` only |
| EIA / OpenEI URDB | Free API keys | API OK | Cache |
| CEC ZEV / CA DMV fuel-type by ZIP | CA open data / CEC dashboard | Download OK | Cache CA files |
| PG&E tariff PDFs | Published tariffs; copyright on PDF text | Manual / LLM extract once, cache JSON | Do not republish full PDFs in repo |
| LoopNet / Crexi | **ToS prohibit scraping** | **FORBIDDEN** | Never a rent source. Rent is the bundled broker seed, ACS/GSA adjustment, and the fallback chain below |
| CBRE / Cushman public MarketBeats | Copyrighted reports; fair-use of published headline rents | Manual entry of headline $/SF into `defaults/` | Cite report; no PDF dump in git |
| Teardown sites / Munro-style | Copyrighted | **No verbatim text in repo** | Optional user-entered unit costs only |
| County assessor | Varies by county; often public | Prefer official CSV/API | San Mateo assessor as demo fallback |

## Concrete datasets

### 1. Census ACS 5-Year (demographics / income / vehicles)

- **Docs:** https://www.census.gov/data/developers/data-sets/acs-5year.html
- **API (2024 vintage example):** `https://api.census.gov/data/2024/acs/acs5`
- **ZCTA example:** `.../acs5?get=NAME,B01003_001E,B19013_001E&for=zip%20code%20tabulation%20area:94402&key=KEY`
- **Block group:** `for=block%20group:*&in=state:06%20county:081`
- **Key needed:** Yes (free) — https://api.census.gov/data/key_signup.html
- **Size:** Small per-ZIP JSON; full national pulls large — prefer on-demand ZCTA + catchment BGs.
- **Refresh:** Annual (ACS 5-year release). Stale if `as_of` > 18 months.
- **Offline:** Cache responses keyed by `(dataset, year, geoid, variables)`.

### 2. Census TIGER geometries

- **ZCTA5 (2025):** https://www2.census.gov/geo/tiger/TIGER2025/ZCTA520/tl_2025_us_zcta520.zip (~505 MB)
- **Block groups:** state extracts via https://www.census.gov/cgi-bin/geo/shapefiles/index.php (Block Groups) or TIGERweb GeoJSON for county subsets.
- **Key:** None.
- **Strategy:** Do **not** ship full US ZCTA in the EXE. First run: download national ZCTA once into user data dir **or** fetch county BG shapefile for queried state; simplify with geopandas; store GeoJSON blobs in SQLite / parquet beside DB. San Mateo demo can ship a small pre-baked GeoPackage under `data/demo/`.

### 3. BLS OEWS — auto technician wages (SOC 49-3023)

- **Tables:** https://www.bls.gov/oes/tables.htm (May 2025 metro XLSX)
- **API:** https://api.bls.gov/publicAPI/v2/timeseries/data/ (OEWS series IDs; free key recommended)
- **Occupation:** SOC **49-3023** Automotive Service Technicians and Mechanics; also consider 53-3000 / office SOCs for staffing mix.
- **Geography:** Metropolitan / nonmetropolitan area files; map ZIP→CBSA via HUD crosswalk.
- **Refresh:** Annual (May OEWS). Stale > 18 months.
- **Offline:** Store metro×SOC mean/median wage table in SQLite.

### 4. BLS QCEW (county industry wages)

- **Downloads:** https://www.bls.gov/cew/downloadable-data-files.htm
- **Open CSV slices:** https://www.bls.gov/cew/additional-resources/open-data/csv-data-slices.htm
- **Note:** NAICS industry, not SOC. Use auto dealer / repair NAICS as **county scaler** vs OEWS metro occupation wage.
- **Refresh:** Quarterly (~6 month lag). Stale > 4 quarters.

### 5. California EV / ZEV registration by ZIP

- **CEC Light-Duty Vehicle Population:** https://www.energy.ca.gov/data-reports/energy-almanac/zero-emission-vehicle-and-infrastructure-statistics-collection/light
- **Bulk XLSX:** https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data → `Vehicle_Population_Last_updated_04-28-2026_ada.xlsx` (~7.8 MB)
- **CA DMV fuel type by ZIP (data.ca.gov):** https://data.ca.gov/@california-department-of-motor-vehicles/vehicle-fuel-type-count-by-zip-code (~32–33 MB CSV per vintage)
- **Key:** None for file download.
- **Refresh:** CEC ~annual (April); DMV vintages listed on portal. Stale > 18 months.
- **Non-CA:** DOE AFDC / state open data; else flag `ev_proxy=acs_national_fallback`.

### 6. HUD–USPS ZIP crosswalk

- **Portal:** https://www.huduser.gov/portal/datasets/usps_crosswalk.html
- **API:** https://www.huduser.gov/portal/dataset/uspszip-api.html
- **Base:** `https://www.huduser.gov/hudapi/public/usps` (Bearer token)
- **Use:** ZIP↔tract, ZIP↔county, ZIP↔CBSA.
- **Key:** Free HUD User token.
- **Refresh:** Quarterly. Stale > 2 quarters.

### 7. Electricity — utility, then state, then national

`estimate` reads `data/seed/electricity_commercial.csv` and `data/seed/county_utility.csv`. It does not call the network. A curator refreshes the files with `scripts/build_local_cost_seeds.py` after downloading the workbooks. `dce.data.ingest.eia_rates.fetch_state_commercial_rate` can download Table 5.6.A (allowlisted `eia.gov`). `dce.data.ingest.openei_urdb.fetch_urdb_rate` can download one approved schedule when `OPENEI_API_KEY` is set. Neither function runs inside `estimate`.

Fallback, first hit wins:

1. **Utility tariff.** The county's utility has a `pge_pdf` or `openei` row. PG&E (EIA utility `14328`) keeps Schedule B-10: $0.2875/kWh and $20.50/kW-month, effective 2026-03-01. https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_B-10.pdf
2. **Utility average.** That utility's EIA-861 2024 commercial revenue divided by bundled plus delivery megawatthours. `demand_rate_kw` is 0. The average is revenue per kWh, so demand charges, customer charges, and riders are already in it. Adding a demand charge on top would count them twice. https://www.eia.gov/electricity/data/eia861/
3. **State.** EIA Electric Power Monthly Table 5.6.A, commercial, August 2026 (cents per kWh, stored as $/kWh). Demand is 0 for the same reason. https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a
4. **National.** The U.S. total on that table, $0.1447/kWh. Demand is 0.

The county's utility is the EIA-861 service-territory utility with the largest commercial megawatthours (bundled plus delivery, not energy-only, so choice kWh are not counted twice). A tie goes to the lower utility id. A county name that matches two census counties, or an EIA county that does not match the crosswalk, is left unassigned and the state price is used (30 unmatched and 6 ambiguous on this build). A large investor-owned utility can outrank a local cooperative under the megawatthour rule. Washakie County, Wyoming, resolves to PacifiCorp on that rule.

OpenEI is a parser for a future tariff row. A tariff replaces the utility average. It is not stacked on the average.

### 7b. Commercial property tax

`data/seed/property_tax_commercial.csv`. Lincoln Institute and Minnesota Center for Fiscal Excellence, 50-State Property Tax Comparison Study, taxes paid in 2024, published July 2025. https://www.lincolninst.edu/publications/other/50-state-property-tax-comparison-study-2024/ (PDF: https://storage.pardot.com/153411/1752612066Gz0HJh4H/50_state_property_tax_comparison_for_2024.pdf, 112 pages, sha256 `b845fc72f646f332fa8312e7e54f3945cdf1daeb4f8a39e16561fd3d4a8ddecb`, retrieved 2026-11-09).

**Class.** Commercial, not homestead. Every row comes from Appendix Table 3a (largest city in each state), 3b (50 largest cities), or 3c (rural municipalities): the $1 million land-and-building parcel with $200,000 of fixtures. The homestead tables (2a–2h) are not used. New York City is 1.418% commercial (Table 3a and 3b, bill $17,014), against 1.249% homestead (Table 2a) and 0.477% homestead with assessment limits (Table 2b). The 1.418% is the commercial rate, not a homestead rate.

**Rate on real property.** `effective_rate` is what the model applies. It is the tax on land and building per dollar of land and building, because the landlord's tax that NNN rent passes through is on the building. The study divides the whole bill by $1.2 million. Where fixtures are fully exempt (Table 4g: DE, HI, IL, IA, MA, MN, NH, NJ, NY, ND, OH, PA, SD; Montana, whose first $1 million of personal property is exempt; Vermont's rural Hartford), the bill is all on the $1 million of real property, so `effective_rate` is the $1 million bill / $1,000,000. New York City is $17,014, 1.7014%. Everywhere else the published rate is kept as the real-property rate. Where fixtures are taxed at a reduced rate, that is a small understatement. `commercial_rate` keeps the published figure, `commercial_tax_bill_1m` the bill.

**Industrial.** `industrial_rate` is the study's industrial figure for the same place (Tables 4a, 4c, 4e: $1 million real property plus $1 million of machinery, inventory, and fixtures, divided by $2 million). It is in the provenance and is not applied. Its denominator is half personal property, and a delivery center's landlord pays on the building. New York City is 0.532% industrial.

`scripts/build_local_cost_seeds.py --only property-tax --lincoln-text FILE` parses `pdftotext -layout` output of the PDF. It checks that each table has 53, 50, or 50 rows, that each industrial row matches the commercial row's city, that each fixture-exempt bill equals 1.2 × the published rate on $1 million, and that the 1.755% 53-city average and every previously transcribed rate still match. The PDF is not in git. `lincolninst.edu` is not on the runtime allowlist.

Fallback, first hit wins:

1. **County.** The ZIP's county is one of the studied cities or the studied rural municipality.
2. **CBSA.** The county is not studied but shares its CBSA or metropolitan division (then the parent CBSA) with a studied large city in the same state. Several matches are averaged. San Mateo County (division 41884) uses San Francisco, 1.171%. Before this change it used Los Angeles, 1.200%. Marin (division 42034) averages San Francisco and Oakland. New York City and Chicago never stand in for a neighbour, because the study treats their systems as unlike the rest of their states, so Westchester and Nassau use Buffalo. Rural municipalities never stand in for a metro. Bergen County, NJ uses Newark.
3. **State rural.** The county is outside every metro and micro area (`cbsa` is empty) and is not itself a studied county. The rung is that state's rural place.
4. **State urban.** Any other county. The rung is the largest city, except Illinois (Aurora, not Chicago) and New York (Buffalo, not New York City).
5. **National.** The mean of the 53 Table 3a cities on the real-property basis, 1.862%. The published 53-city average, 1.755%, is `commercial_rate`.

`property_tax.included_in_nnn` stays true. The local rate does not add a second tax line. It shifts `opex_load`:

`opex_load = 0.15 + assessed_value_psf × (local_rate − 0.011) / rent_psf_year`

`assessed_value_psf` stays 250. At the reference rate 1.1% the load stays 0.15. A zero rent is not shifted. The result is never negative. Insurance and CAM stay inside the 15% base. No public commercial-insurance index is applied.

### 9. Build / fit-out cost index

Fit-out uses a construction-cost location factor: the DoD MILCON area cost factor (ACF), UFS 3-701-01 *DoD Facilities Pricing Guide*, 6 June 2026, Table 4-1 CONUS. Data tables workbook https://legacy.wbdg.org/FFC/DOD/UFC/ufs_3_701_01_2026_Data_Tables.xlsx (sha256 `3bf160445a24eb53ff015301f6f3d8f7ade6710b8e1c9ed351ea8e203b8ff28a`), document https://legacy.wbdg.org/FFC/DOD/UFC/ufs_3_701_01_06_2026.pdf, index page https://www.wbdg.org/dod/ufc/ufc-3-701-01. Retrieved 2026-11-09. Source date of the tables 2025-10-01. Approved for public release, distribution unlimited (US government work).

The Tri-Service ACF prices 8 labor crafts, 18 materials, and 4 equipment items (weights 63/35/2), adjusts for weather, seismic, climate, labor availability, overhead and profit, logistics, and productivity, and is normalized so the 96 DoD base cities (two per contiguous state) average 1.00. The fit-out assumption, $100 per square foot, is a national figure, so it is multiplied by the ACF directly.

`data/seed/construction_cost_factor.csv`, built by `scripts/build_local_cost_seeds.py --only construction-cost --dod-xlsx FILE`. Columns `level, geography_id, state, name, acf, count, as_of, source, citation`. The workbook lists 15,549 DoD sites. A site's county comes from its state and county name, or from its ZIP when the name is missing or matches two counties. 14 sites matched neither and are skipped. A county row is the lower median of its sites (1,987 counties). A CBSA row (metropolitan division and parent CBSA) and a state row are the lower medians of their county rows, so one large installation does not set a whole state. CBSA rows are kept only where some county has no row of its own (192). The lower median keeps every stored value a published DoD value.

| Place | DoD ACF | BEA goods index (old) |
|---|---|---|
| Manhattan (New York County) | 1.32 | 1.107 |
| San Francisco County | 1.32 | 1.089 |
| San Mateo County (94402) | 1.23 | 1.089 |
| Miami-Dade County | 0.87 | 1.040 |
| Travis County (Austin) | 0.82 | 0.942 |
| Washakie County, WY (Worland) | 1.05 | 0.958 |

Fallback, first hit wins: county, then CBSA (`GeoContext.cbsa`, then the parent CBSA of a division), then state, then the BEA 2024 goods regional price parity over the U.S. goods parity (metro, then state; `data/seed/bea_rpp_2024.csv`, released 2026-02-19, https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area), then 1.00. The DoD table covers every state and DC, so BEA is reached only for places such as Puerto Rico, and BEA has no Puerto Rico row either, so those ZIPs stay at 1.00. The BEA index is still resolved and quoted in the `fitout_index` provenance detail.

The DoD states that the MILCON ACF is for construction cost only and should not adjust detailed commercial unit-price estimates. Here it scales one national $/SF fit-out allowance, which is a programming-level use. Equipment stays the national catalog price. Only fit-out is indexed. RSMeans and ENR city cost indexes are proprietary and are not copied. RLB, Cumming, and Turner publish a few dozen cities each, not counties, so they are not the seed. `wbdg.org` is a curator host, not a runtime host.

### 9b. What stays national

These inputs are still one number for every ZIP. A public regional series was not applied, for the reason in the last column.

| Input | Value | Why it stays national |
|---|---|---|
| Delivery fee | $1,390 | Tesla posts one fee. There is no public ZIP fee schedule. |
| Inbound freight | $150 | The assumptions file's carrier-minimum figure. No public lane index is in the seed. Distance is not invented. |
| Other opex | 8% of lease + labor | The base is already local once rent and wages are local. Scaling it again by a price parity would count the same difference twice. |
| State income tax and depreciation | California 8.84%, California nonconformity | The DCF is Tesla's consolidated return, not a site-level return. |
| Overtime multiplier | 1.5 | FLSA, not a California-only rule. |
| Equipment capex | assumptions catalog | No public equipment price index. Fit-out carries the DoD construction area cost factor. |
| Building size, kWh per square foot, peak kW, staffing, WACC | assumptions file | Operating assumptions, not a Bay Area price. |
| Insurance and CAM | inside the 15% NNN load | The tax slice of that load moves with section 7b. No separate public insurance index. |
| Delivery volume outside California | Cox/KBB residual, by ZIP | `estimate` allocates the national Tesla total minus California. It does not hold every ZIP at 4,500. |
| Wage | OEWS SOC 49-3023 | The metro mean when the parent CBSA publishes it, otherwise the national row. The delivery-role mix is not substituted for that series. |
| Rent | `resolve_rent` ladder | An observed industrial seed is used as published. The ACS factor is not applied on top of it. 94402 stays the Kidder Mathews $2.14. |

`MODEL_VERSION` is `2026.11.6-commercial-tax-acf` (`dce.precompute.version`). A precomputed row is stale when its stored model version or inputs hash differs. The hash covers the electricity, property-tax, construction-cost, and price-index seeds. `assumptions_version` stays `2026.11.2`. The golden cost fixtures do not move, because `build_cost_inputs` keeps the assumptions values when the new arguments are omitted.

### 8. Automatic commercial rent (ZERO manual input)

**Confirmed by Jacob on 2026-11-09.** User types a US ZIP. Rent $/SF resolves with no required form fields. An optional advanced override may exist for sensitivity checks; the default path must not need it. Never scrape LoopNet or Crexi.

#### Evaluation (verified 2026-11-08 PT)

| Option | Cost | ZIP granularity | Student-feasible? | Notes |
|---|---|---|---|---|
| **Public broker MarketBeats** (CBRE, Cushman, Colliers, JLL) | Free PDFs | Metro / submarket, not ZIP | **Yes (curated seed)** | Industrial asking $/SF/yr published quarterly; cite + enter into seed CSV — do not scrape PDFs at runtime |
| **GSA Lease Inventory** | Free | Often ZIP + city/state; monthly XLSX ~1 MB | **Yes** | https://www.gsa.gov/real-estate/realty-and-lease-acquisition — `Current Annual Rent` / `Lease Agreement RSF` → $/SF; mostly **office/gov**, use as calibrator + sparse ZIP prior, not pure industrial truth |
| County assessor / CAMA open data | Free where published | Parcel | Partial | Coverage uneven; good for SM demo later, not national v1 |
| HUD FMR / Small Area FMR | Free API + XLSX | County / ZIP (SAFMR) | Yes as **weak** proxy | https://www.huduser.gov/portal/datasets/fmr.html · API https://www.huduser.gov/portal/dataset/fmr-api.html — **residential** |
| Zillow ZORI (ZIP) | Free research CSV | ZIP | Yes as **weak** proxy | https://www.zillow.com/research/data/ — residential; check Zillow research terms for redistribution of derived seed |
| Census ACS (income, density, home value B25077) | Free | ZCTA | Yes as **adjusters** | Not rent itself; used in ZIP-within-metro regression |
| CoStar | Academic portal / enterprise; no public API; ~$300–800+/seat/mo reported | Property | **No for offline EXE** | Academic Engagement is university-licensed UI, not redistributable API in a desktop app |
| CompStak | From ~$200/user/mo; API quote | Market/property | **No (cost)** | |
| Reonomy | From ~$400/user/mo; API quote | Property | **No (cost)** | |
| ATTOM | Basic Property API from ~$500/mo | Property | **No (cost)** | |
| Crexi Listing API | Partnership / agreement; not self-serve | Listings | **No** | Scraping still ToS-forbidden; API is invite-only |
| Cherre / Moody’s CRE metro DBs | Enterprise | Metro | **No (cost)** | |
| LoopNet / Crexi HTML | — | — | **FORBIDDEN** | ToS prohibit scraping |

#### Recommended primary approach

1. **Ship a bundled seed** `data/seed/rent_cbsa_industrial.parquet` (or SQLite rows): CBSA → industrial asking rent $/SF/year, `as_of`, `citation_url`, `broker` (CBRE/Cushman/…).
2. **ZIP → CBSA** via HUD–USPS crosswalk (also seeded for offline).
3. **ZIP adjustment (deterministic):**\
   `rent_zip = rent_cbsa × f(ACS_zcta)` where `f` is a frozen linear model (coefficients in `rent_model_coeffs`) trained offline on (GSA $/SF ∪ broker metro rents) vs ACS income, density, median home value. No network, no LLM.
4. **Property-type note:** For delivery-center narrative use **industrial / flex** asking rents; if only office GSA comps exist for a ZIP, down-weight and flag confidence.

#### Deterministic fallback chain (shipped 2026-11-09)

`resolve_rent` implements this chain. The Python fields are in
`docs/contracts/zip_data.md`. ZORI is not in the seed (redistribution terms).

```
1. broker_county            broker market rent for the ZIP's county (borough / submarket)   high (medium for office_showroom_proxy)
2. cbsa_raw                 observed industrial seed (Kidder 41884), not ACS-scaled          high
3. broker_cbsa              broker market rent for the ZIP's CBSA or metro division          high
4. county_gsa               GSA median; ACS factor only when no CBSA seed
5. state / national         rent_cbsa industrial seeds (state needs ≥3 CBSA seeds; national is CBSA 00000)
6. hud_safmr                2-bedroom monthly, converted
7. acs_gross_rent           this ZCTA's B25064
8. acs_gross_rent_county    then _cbsa, _state, _national medians of B25064
```

`rent_cbsa.csv` still has one row: CBSA `41884`, $25.68/sf/year
($2.14/sf/month), as_of 2026-09-30, Kidder Mathews Peninsula Industrial
Market Report Q3 2026
(https://kidder.com/market-reports/peninsula-industrial-market-report/).
That rate is used as published for every ZIP in `41884`, including
`94402`, and it keeps precedence over any CBSA broker row.

`rent_market.csv` (model `2026.11.7-broker-rents`) adds 50 broker rows:
29 CBSAs or metro divisions and 21 counties, all Cushman & Wakefield
MarketBeat Q3 2026 (as_of 2026-09-30). Each row has `source`, `report`,
`quarter`, `url`, the figure as printed (`reported_rent`, `reported_unit`,
`reported_basis`), the annual NNN equivalent (`rent_psf_year`), and a
`note` naming the table row and column used. Coverage: NYC boroughs
(Manhattan, Bronx, Brooklyn, Queens, Staten Island), Nassau, Suffolk,
North and Central New Jersey counties, Los Angeles, Orange County, Inland
Empire, San Diego, East Bay (36084), Silicon Valley (41940), Seattle,
Tacoma, Portland, Phoenix, Denver, Las Vegas, Salt Lake City, Boston,
Cambridge-Newton-Framingham, Washington DC (11694 and 47764),
Frederick-Gaithersburg-Bethesda, Chicago, Lake County IL, Miami, Fort
Lauderdale, West Palm Beach, Austin, Dallas, Fort Worth, Houston, Atlanta,
Philadelphia, and Camden.

**Rent type.** A delivery center is a light-industrial, flex, or showroom
site. The curator takes the report's flex column (High Tech/Flex, Office
Service/Flex, IMT/Flex, or FX) from the most specific row that covers the
mapped geography (`industrial_flex`). When the report publishes no flex
rent there, the overall weighted industrial rent is used
(`industrial_overall`). Manhattan has no industrial inventory in the C&W or
CBRE industrial reports; showroom and flex space there leases in the
office and loft market, so 36061 uses the Manhattan office overall asking
rent (`office_showroom_proxy`, confidence medium).

**Units.** Every row is converted to annual NNN dollars per square foot by
`dce.data.rent_defaults.nnn_rent_psf_year`: monthly × 12; NNN or net used
as is; full-service gross ÷ (1 + 0.15), the shipped `facility.opex_load`
base, because the model adds the NNN load back on top of rent. The reader
rejects a row whose stored `rent_psf_year` does not match that conversion.

**Geography.** County rows come first, so a borough beats its metro.
`rent_market` rows do not feed the state-median rung, so a metro rent never
spreads to rural ZIPs in the same state. A ZIP in a covered CBSA but an
uncovered county (Westchester in 35614, for example) still falls to ACS.
`acs_rent_v1` never scales a broker row.

ZIPs with no broker row use SAFMR or their own ACS `B25064` rent, then the
county, CBSA, state, and national median of that rent. Conversion is
monthly × 12 / 1000. The ratio is 1 until a GSA fit. Those rungs are
`residential_proxy` at low confidence.

UI shows: resolved `$/SF/yr`, **source tier**, **confidence**, **as_of**, staleness badge. Never a blank requiring typing.

#### SQLite rent tables (cache + seed)

```sql
-- Bundled seed copied into user DB on first launch
rent_cbsa (
  cbsa TEXT PK, property_type TEXT,  -- 'industrial'|'flex'|'retail'|'auto_service'
  rent_psf_year REAL, as_of TEXT, citation TEXT, broker TEXT, fetched_at TEXT
);
rent_zip_obs (
  zip TEXT, property_type TEXT, rent_psf_year REAL, as_of TEXT,
  source TEXT,  -- 'gsa'|'assessor'|'model'
  n_leases INT, citation TEXT, PRIMARY KEY(zip, property_type, source, as_of)
);
rent_model_coeffs (
  model_id TEXT PK, formula_json TEXT, trained_on TEXT, as_of TEXT
);
rent_resolved_cache (
  zip TEXT PK, rent_psf_year REAL, property_type TEXT, tier TEXT,
  confidence TEXT, as_of TEXT, components_json TEXT, resolved_at TEXT
);
-- Migration 8. Copied from data/seed/rent_market.csv and kept in sync with it.
rent_market (
  geography_level TEXT,  -- 'county'|'cbsa'
  geography_id TEXT, market TEXT, submarket TEXT,
  property_type TEXT,    -- 'industrial_flex'|'industrial_overall'|'office_showroom_proxy'
  rent_psf_year REAL,    -- annual NNN equivalent
  reported_rent REAL, reported_unit TEXT, reported_basis TEXT,
  source TEXT, report TEXT, quarter TEXT, as_of TEXT, url TEXT, note TEXT, fetched_at TEXT,
  PRIMARY KEY(geography_level, geography_id)
);
```

**Bundled seed in the Mac .app / Windows EXE:** national CBSA industrial table (tens–low hundreds of metros), HUD ZIP→CBSA for all ZIPs (or on-demand with seed for CA+top metros), `rent_model_coeffs`, San Mateo demo GSA/broker rows. App works **offline before any network** using seed; refresh updates seed tables when online.

**Refresh cadence:** Broker seed quarterly (manual curator script, not runtime scrape); GSA monthly; ACS annual; HUD FMR annual; ZORI monthly if used. Stale thresholds: broker > 2 quarters → aging; > 4 → stale; GSA > 90 days → aging.

### 10. Existing US Tesla delivery centers (catchment competitors)

**Output:** `data/seed/tesla_delivery_centers_us_2026-11-08.csv`, built by `scripts/build_us_delivery_centers.py`. `dce.data.ingest.delivery_centers.load_us_delivery_centers` returns every row. `load_delivery_centers` returns only the ten Bay Area research rows (`dce_research_20261108`), because the M3.5a 94402 goldens were calibrated on those nine delivery centers. With the national list, Stockton, Seaside, and Sacramento fall inside the 60-mile cap and move 94402 gravity from 5,522.8 to 5,483.3 deliveries a year. `as_of` is `2026-11-08` on every row. The loader never uses the network. Only the build script does, and only when a curator runs it.

**Why no live tesla.com fetch.** `tesla.com` answers HTTP 403 to scripted requests, and it is not on the public-data allowlist. The script never contacts it. It reads public copies and public datasets only. Tesla internal data is never used.

| Source id (`source` column) | What it is | URL | Accessed (PT) | Licence / terms | Used for |
|---|---|---|---|---|---|
| `tesla_findus_wayback_20241214` | Tesla's public Find Us US delivery-center list, Internet Archive capture `20241214220441` (newest US capture) | https://web.archive.org/web/20241214220441/https://www.tesla.com/findus/list/deliverycenters/United+States | 2026-11-08 | Tesla page, archived by the Internet Archive. Only facts are kept: name, street address, city, state, ZIP. No page text or images are committed except the small markup excerpt in `tests/fixtures/delivery_centers/` | The list of record. 118 entries in 27 states |
| `alltheplaces_tesla_20261017` | All the Places run `2026-10-17-13-32-31`, spider `tesla` (reads the public Find Us sales and service locations) | https://alltheplaces-data.openaddresses.io/runs/2026-10-17-13-32-31/output/tesla.geojson | 2026-11-08 | CC0 1.0 (All the Places output) | Evidence that a listed center still existed in October 2026. Fallback coordinates. Delivery-named sites not on the list (`possible_handover`) |
| `osm_overpass_20261108` | OpenStreetMap Tesla `shop=car` / `shop=car_repair` in the US, from the Overpass API (query in the script) | https://overpass-api.de/api/interpreter | 2026-11-08 | ODbL 1.0, © OpenStreetMap contributors | A second check only. No OSM geometry is stored in the seed |
| *(coordinates)* | U.S. Census Bureau batch geocoder, benchmark `Public_AR_Current` | https://geocoding.geo.census.gov/geocoder/locations/addressbatch | 2026-11-08 | Public domain (US Government work) | `lat`/`lon` for 96 rows (`coordinate_basis` `census_geocoder_current`) |
| *(coordinates, fallback)* | Nominatim (OSM) search, at most one request a second, only for rows that neither the Census geocoder nor All the Places can place | https://nominatim.openstreetmap.org/search | not needed on 2026-11-08 | ODbL 1.0; Nominatim usage policy | Last-resort geocode (`nominatim_osm`, or `nominatim_osm_street` for a road-level hit). The 2026-11-08 build used it for 0 rows |
| `dce_research_20261108` | The ten Bay Area rows in `data/seed/tesla_delivery_centers_2026-11-08.csv`: the live Find Us list as read in a browser on 2026-11-08 for the catchment research, plus the North San Jose hub | `docs/research/tesla_delivery_ops_research.md` §1.1 and §1.6 | 2026-11-08 | Facts from a public page; Census 2024 Gazetteer ZCTA internal points (public domain) | Copied over unchanged, with their ZCTA internal-point coordinates, so the M3.5a catchment goldens still hold |

**Host allowlist (build script only).** `ALLOWED_HOSTS` in `scripts/build_us_delivery_centers.py`: `web.archive.org`, `alltheplaces-data.openaddresses.io`, `overpass-api.de`, `geocoding.geo.census.gov`, `nominatim.openstreetmap.org`. HTTPS only. Redirects and URLs with embedded credentials are refused. Downloads are cached under `data/cache/us_centers/` (gitignored), so a rebuild from that cache is offline and byte-identical. `--refresh` downloads everything again. None of these hosts is on the app's runtime allowlist, and the app never fetches them.

**Merge rules.**

1. The Bay Area research rows are copied first. A Find Us row in one of their ZIPs is not added again.
2. Every other Find Us row is kept if it can be placed. The order is the Census geocoder, then the All the Places point for the same center (same slug, or same house number and ZIP), then Nominatim. A row that none of these can place is dropped and reported. It is not guessed.
3. An All the Places site whose own slug or name says "deliver", and that matches no Find Us row, becomes `location_type` `possible_handover`.
4. Locations are never invented. Every `address` in the seed appears in one of the inputs above.

**Confidence rules (`confidence` column).**

| Level | Rule |
|---|---|
| `high` | On the 2024-12-14 Find Us delivery list and present in the 2026-10-17 All the Places run, or a 2026-11-08 research row on the live list |
| `medium` | On the 2024 list, not in the 2026 run, but an OSM Tesla shop has the same house number and ZIP or is within 300 m. The North San Jose hub is also `medium` because it was not on the Find Us list |
| `low` | On the 2024 list with no 2026 evidence. Or in a state that the 2026-11-08 research read of the live list showed with no delivery centers (Texas; `STATES_OFF_LIVE_LIST`). Or a `possible_handover` site |

Downstream code may filter on `confidence` (for example, keep `high` and `medium` for the headline catchment and use `low` rows for a sensitivity case).

**Known gaps.** The live list on 2026-11-08 had 135 entries (CA 31, FL 19, IL 9, WA 6; research §1.1). The 2024 capture has 118. Centers opened after December 2024 are missing unless the research list or All the Places names them. They are not added by hand. The seed is a lower bound on competing centers.

**Refresh.** TTL 90 days (`DELIVERY_CENTER_TTL_DAYS`). To refresh, run `python scripts/build_us_delivery_centers.py --refresh`. If a newer Wayback capture or All the Places run exists, update `FINDUS_CAPTURE` / `ATP_RUN` and the source ids, and rename the output file to the new `as_of`.

### 11. Nationwide ZIP inputs (map click)

Accessed **2026-11-09**. Counts are `data/seed/coverage.json`. The Python API is `docs/contracts/zip_data.md`. Rebuild with `make zip-inputs` and `make zcta-boundaries`. Those targets are not part of `make check`. Tests use fixtures and the committed extracts. They do not download.

The runtime allowlist is unchanged: `census.gov`, `bls.gov`, `huduser.gov`, `eia.gov`, `openei.org`, `energy.ca.gov`, `data.ca.gov`, `pge.com`. `data.hrsa.gov`, `bea.gov`, `lincolninst.edu`, and `wbdg.org` are curator hosts only. They are not added to `dce.data.ingest.http`. `estimate` reads the committed CSVs.

| Input | File in `data/seed/` | Source | URL | Licence |
|---|---|---|---|---|
| ZCTA internal points | `zcta_centroid_2024.csv` (33,791) | Census 2024 Gazetteer | https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip | Public domain (US government work). `as_of` `2024-01-01` |
| ZIP to county, CBSA, ZCTA | `zip_crosswalk.csv` (41,034 ZIPs, 54,196 ZIP-county rows, 33,791 ZCTAs, 26,524 ZCTAs with a CBSA) | Census 2020 ZCTA-to-county relationship, land-area share, plus the July 2023 CBSA delineation (list 1). `list1_2024.xlsx` was HTTP 404 on this date, so 2023 is the file | https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt and https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx | Public domain. `GeoContext.cbsa` is the metropolitan division when list 1 has one (`41884` for San Mateo, not parent `41860`) |
| ZIP Codes that are not ZCTAs | same crosswalk | HRSA GeoCare Navigator ZIP Code to ZCTA Crosswalk, 2025. Exact duplicate rows are collapsed. A blank ZCTA is skipped | https://data.hrsa.gov/DataDownload/GeoCareNavigator/ZIPCodetoZCTACrosswalk2025UDS.xlsx (index https://data.hrsa.gov/GeoCareNavigator/Resources) | US government work (HHS/HRSA). Not a runtime host |
| Households, population, income, rent, home value, vehicles | `zcta_acs_2024.csv` | ACS 2024 5-year table-based summary files, ZCTA rows (`GEO_ID` prefix `860Z200US`). No API key. Summary column `B01003_E001` is API `B01003_001E` | https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/ | Public domain. `as_of` `2024-12-31` |
| Metro wages | `oews_metro_2025.csv` (403 rows) | BLS OEWS via `https://api.bls.gov/publicAPI/v2/timeseries/data/` (v1 when `BLS_API_KEY` is unset). May 2025. SOC `49-3023` mean and median for 392 of 393 metropolitan parent CBSAs. Guayama, PR (`25020`) returned no annual series. Delivery SOCs for the nation (`00000`) and for `41860`. The `www.bls.gov` bulk zip answered HTTP 403 from this environment, so the seed is the API extract. `parse_oews_bulk_csv` can read a curator CSV later | https://www.bls.gov/oes/tables.htm | Public domain. `as_of` `2025-05-01`. All 37 divisions map to the parent CBSA before the lookup |
| Industrial rent | `rent_cbsa.csv`, `rent_model_coeffs.json` | One cited Kidder Mathews headline. Coefficients are the shipped `acs_rent_v1` defaults, not a GSA fit | https://kidder.com/market-reports/peninsula-industrial-market-report/ | Headline figure and citation only. No PDF in git |
| Commercial electricity | `electricity_commercial.csv`, `county_utility.csv` | EIA-861 2024 utility averages, EIA Table 5.6.A August 2026 state and US prices, PG&E B-10 for utility 14328 | https://www.eia.gov/electricity/data/eia861/ and https://www.eia.gov/electricity/monthly/xls/table_5_06_a.xlsx | US government work, plus the published PG&E schedule. `as_of` 2024-12-31 (861), 2026-08-31 (EPM), 2026-03-01 (B-10) |
| Commercial property tax | `property_tax_commercial.csv` | Lincoln Institute / MCFE 50-State study, taxes paid in 2024, commercial class (Tables 3a–3c, $1 million building + $200,000 fixtures) on real property; industrial (Tables 4a, 4c, 4e) for reference | https://www.lincolninst.edu/publications/other/50-state-property-tax-comparison-study-2024/ | Rates parsed from the PDF text, with a citation. The PDF is not in git. `as_of` 2024-12-31 |
| Construction cost factor | `construction_cost_factor.csv` | DoD UFS 3-701-01 (6 June 2026) Table 4-1 CONUS MILCON area cost factor, by county, CBSA, and state. Fit-out index | https://legacy.wbdg.org/FFC/DOD/UFC/ufs_3_701_01_2026_Data_Tables.xlsx | US government work, approved for public release. `as_of` 2025-10-01 |
| Goods price parity | `bea_rpp_2024.csv` | BEA Regional Price Parities, 2024, goods and all-items. Fit-out fallback only (goods / U.S. goods) | https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area | US government work. `as_of` 2024-12-31. Released 2026-02-19 |
| California ZEV sales | `zev_zip_sales.csv`, `zev_county_sales.csv` | CEC New ZEV Sales workbook, newest year in the file (2026): 7,953 ZIP rows, 4,082 county rows | https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data (file used: https://www.energy.ca.gov/filebrowser/download/10036?fid=10036) | California Energy Commission open data. Outside California, `ev_proxy` is `acs_national_fallback`. No invented state Tesla total |
| HUD ZIP API | not the shipped crosswalk | `https://www.huduser.gov/hudapi/public/usps` type 2 and type 3. The docs page returned an HTTP 202 WAF challenge on this date, so the parser follows the published `data.results[].geoid` / `tot_ratio` / `state` shape and was not verified live | https://www.huduser.gov/portal/datasets/usps_crosswalk.html | US government work. Needs `HUD_TOKEN`. Missing token raises before any socket |

ACS coverage among 33,772 ZCTA rows in the 2024 summary files: population 33,772, households 33,772, median household income 30,547, median home value 30,260, aggregate vehicles 28,665, median gross rent 25,751. The 19 Gazetteer ZCTAs that are absent from ACS stay in the crosswalk with null ACS fields. Census sentinels on an estimate become null. A margin-of-error sentinel does not null the estimate. `94402` matches the demo cache: population 25,475, households 10,125, income 172,522, vehicles 18,262, home value 2,000,001, median gross rent 3,501, internal point 37.540103, -122.330103, land 5.05 square miles.

#### ZCTA polygons

Census has not published a national ZCTA cartographic file since 2020 (the 2024 GENZ directory has no ZCTA zip). The 2024 gazetteer still says ZCTAs follow 2020 tabulation blocks.

- **File:** https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip (1:500,000, code `ZCTA5CE20`). Public domain.
- **Simplify:** Douglas-Peucker, 0.001 degrees (about 111 m), topology preserved, then reprojected to EPSG:4326. The only property is `zcta`.
- **Nationwide asset:** PMTiles vector tiles, layer `zcta`, zooms 3–8, every polygon kept (`tippecanoe --no-feature-limit --no-tile-size-limit`). MapLibre decodes only the tiles in view. A single GeoJSON of the same 33,791 polygons is 71,158,217 bytes and would be parsed all at once, so it is not the runtime asset and it is not committed. `data/geo/zcta_us.pmtiles` is gitignored and is 22,151,345 bytes. `make zcta-boundaries` rebuilds it.
- **Committed fixture:** `data/geo/zcta_bay_area.geojson`, 452,598 bytes, 300 ZCTAs whose dominant county is Alameda, Contra Costa, Marin, Napa, San Francisco, San Mateo, Santa Clara, Solano, or Sonoma. The same numbers are in `data/geo/boundary_build.json`.

`make zip-inputs` reads a cache directory (default `data/cache/zip_inputs`, gitignored). The 2026-11-09 extracts were built from `/tmp/dce-public`. Pass `--fetch-bls` and `--fetch-zev` to call `api.bls.gov` and `energy.ca.gov`. Pass `--download` to fetch the Census and HRSA files. Curator downloads are HTTPS and refuse redirects.

## Offline caching strategy

```
~/Library/Application Support/DeliveryCenterEstimator/   # macOS
%LOCALAPPDATA%\DeliveryCenterEstimator\                  # Windows
~/.local/share/delivery-center-estimator/                # Linux dev
  dce.sqlite          # facts, wages, EV counts, as_of, staleness
  geo/                # simplified GeoJSON / GPKG by state or county
  extract_cache/      # pdf_sha256 → JSON (LLM or manual)
```

API keys stay in a local `.env` (never in git), not inside the user data directory. The bundled seed in `data/seed/` is copied into `dce.sqlite` on first launch so the app works offline before any refresh.

**Fetch policy:** allowlist hosts only (census.gov, bls.gov, huduser.gov, eia.gov, openei.org, energy.ca.gov, data.ca.gov, pge.com). Idempotent loaders; write `source_registry` row with `fetched_at`, `as_of`, `ttl_days`, `url`. Curator seed-build scripts keep their own narrower allowlists (for example §10); the app never calls those hosts.

**Staleness UI:** `fresh` | `aging` | `stale` | `missing` from `now - as_of` vs TTL. M2: `missing` when `as_of` is absent; `fresh` through half of `ttl_days`; `aging` through `ttl_days`; `stale` after that. Eighteen months is 548 days. That half-TTL split is how "aging after 2 quarters, stale after 4" is expressed with one TTL.
