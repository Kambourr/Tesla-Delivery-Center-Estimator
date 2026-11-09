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

### 7. Electricity — EIA + OpenEI + PG&E (demo)

- **EIA retail sales (commercial $/kWh by state):** https://www.eia.gov/opendata/ — `electricity/retail-sales` (API key free)
- **OpenEI URDB:** https://openei.org/services/doc/rest/util_rates/?version=4 · https://api.openei.org/utility_rates
- **PG&E tariff book:** https://www.pge.com/tariffs/en.html
  - B-10: https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_B-10.pdf
  - B-19: https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_B-19.pdf
- **Refresh:** EIA monthly; PG&E on advice-letter cadence — mark PDF `as_of` from advice header. Stale: EIA > 6 months; tariff PDF > 12 months or superseded schedule.

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
1. zip_adjusted_cbsa   industrial seed × acs_rent_v1     high, or medium if clamped
2. county_gsa          median of rent_zip_obs source=gsa
3. cbsa_raw            industrial seed, no ACS factor
4. state               median of industrial seeds, only when that state has ≥3 CBSA seeds
5. national            industrial seed stored as CBSA 00000 (none shipped)
6. hud_safmr           else acs_gross_rent (B25064)      low, residential proxy
```

The shipped industrial seed is one row: CBSA `41884`, $25.68/sf/year
($2.14/sf/month), as_of 2026-09-30, Kidder Mathews Peninsula Industrial
Market Report Q3 2026
(https://kidder.com/market-reports/peninsula-industrial-market-report/).
`acs_rent_v1` uses the ZCTA median gross rent ratio only
(`b_acs_rent = 1`; income, density, and home value exponents are 0 until a
GSA fit). A single Bay Area headline cannot become the California or
national rent. Other ZIPs use their own ACS `B25064` rent, converted as
`monthly * 12 / 1000`, and are marked `residential_proxy` at low confidence.

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
```

**Bundled seed in the Mac .app / Windows EXE:** national CBSA industrial table (tens–low hundreds of metros), HUD ZIP→CBSA for all ZIPs (or on-demand with seed for CA+top metros), `rent_model_coeffs`, San Mateo demo GSA/broker rows. App works **offline before any network** using seed; refresh updates seed tables when online.

**Refresh cadence:** Broker seed quarterly (manual curator script, not runtime scrape); GSA monthly; ACS annual; HUD FMR annual; ZORI monthly if used. Stale thresholds: broker > 2 quarters → aging; > 4 → stale; GSA > 90 days → aging.

### 9. Build / fit-out cost proxies

- Public RSMeans-style indexes or municipal permit valuation averages, stored as assumption defaults (not typed on every run).
- Teardown articles: a single unit cost may be entered as an optional advanced assumption; **do not** commit copyrighted teardown text or tables to the repo.

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

The runtime allowlist is unchanged: `census.gov`, `bls.gov`, `huduser.gov`, `eia.gov`, `openei.org`, `energy.ca.gov`, `data.ca.gov`, `pge.com`. `data.hrsa.gov` is a curator host only (`scripts/build_zip_inputs.py`). It is not added to `dce.data.ingest.http`.

| Input | File in `data/seed/` | Source | URL | Licence |
|---|---|---|---|---|
| ZCTA internal points | `zcta_centroid_2024.csv` (33,791) | Census 2024 Gazetteer | https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/2024_Gaz_zcta_national.zip | Public domain (US government work). `as_of` `2024-01-01` |
| ZIP to county, CBSA, ZCTA | `zip_crosswalk.csv` (41,034 ZIPs, 54,196 ZIP-county rows, 33,791 ZCTAs, 26,524 ZCTAs with a CBSA) | Census 2020 ZCTA-to-county relationship, land-area share, plus the July 2023 CBSA delineation (list 1). `list1_2024.xlsx` was HTTP 404 on this date, so 2023 is the file | https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt and https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx | Public domain. `GeoContext.cbsa` is the metropolitan division when list 1 has one (`41884` for San Mateo, not parent `41860`) |
| ZIP Codes that are not ZCTAs | same crosswalk | HRSA GeoCare Navigator ZIP Code to ZCTA Crosswalk, 2025. Exact duplicate rows are collapsed. A blank ZCTA is skipped | https://data.hrsa.gov/DataDownload/GeoCareNavigator/ZIPCodetoZCTACrosswalk2025UDS.xlsx (index https://data.hrsa.gov/GeoCareNavigator/Resources) | US government work (HHS/HRSA). Not a runtime host |
| Households, population, income, rent, home value, vehicles | `zcta_acs_2024.csv` | ACS 2024 5-year table-based summary files, ZCTA rows (`GEO_ID` prefix `860Z200US`). No API key. Summary column `B01003_E001` is API `B01003_001E` | https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/ | Public domain. `as_of` `2024-12-31` |
| Metro wages | `oews_metro_2025.csv` (403 rows) | BLS OEWS via `https://api.bls.gov/publicAPI/v2/timeseries/data/` (v1 when `BLS_API_KEY` is unset). May 2025. SOC `49-3023` mean and median for 392 of 393 metropolitan parent CBSAs. Guayama, PR (`25020`) returned no annual series. Delivery SOCs for the nation (`00000`) and for `41860`. The `www.bls.gov` bulk zip answered HTTP 403 from this environment, so the seed is the API extract. `parse_oews_bulk_csv` can read a curator CSV later | https://www.bls.gov/oes/tables.htm | Public domain. `as_of` `2025-05-01`. All 37 divisions map to the parent CBSA before the lookup |
| Industrial rent | `rent_cbsa.csv`, `rent_model_coeffs.json` | One cited Kidder Mathews headline. Coefficients are the shipped `acs_rent_v1` defaults, not a GSA fit | https://kidder.com/market-reports/peninsula-industrial-market-report/ | Headline figure and citation only. No PDF in git |
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
