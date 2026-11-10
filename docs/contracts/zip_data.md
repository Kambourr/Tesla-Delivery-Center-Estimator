# ZIP data contract

Public inputs for one US ZIP. The precompute and the MapLibre UI should call
these functions. They do not scrape listing sites and they do not use Tesla
internal data.

`resolve_zip` reads `data/seed/zip_crosswalk.csv` and does not open SQLite.
Everything else reads a database that `load_zip_seed` has filled.
`get_connection` does not load the seed. Call `load_zip_seed` once per database.

## Resolve a ZIP

```python
from dce.geo.resolve import resolve_zip

geo = resolve_zip("94402")
# GeoContext(zip_code="94402", zcta="94402", county_fips="06081",
#            cbsa="41884", state="CA")
```

- The ZIP is 5 digits. Leading zeros stay. `"  94402  "` is accepted.
- `InvalidZipError` means it is not 5 digits. `UnknownZipError` means it is
  absent from the seed (`99999`). Both carry `.zip_code`.
- When a ZIP sits in more than one county, the greatest `tot_ratio` wins.
  A tie goes to the lower county FIPS.
- `cbsa` is the July 2023 metropolitan division when the county has one, and
  the CBSA otherwise. `94401`–`94404` stay division `41884`, not parent
  `41860`. A county outside every metro and micro area has `cbsa == ""`
  (Puerto Rico ZCTA `00601` is one of these).
- A ZIP that is not a ZCTA (a PO box or a single-delivery point) points at
  the HRSA ZCTA. `00501` is ZCTA `11742`, county `36103`, division `35004`,
  state `NY`.

## Load the seed

```python
from dce.data.zip_seed import load_zip_seed

counts = load_zip_seed(conn, fetched_at="2026-11-09T00:00:00Z")
```

Replaces crosswalk, 2024 centroids, 2024 ACS, OEWS wages, the industrial rent
seed, and the `acs_rent_v1` coefficients. When `zev_zip_sales.csv` and
`zev_county_sales.csv` are present, replaces CEC rows (`source = 'cec'`).
DMV rows are left in place.

`counts` is a `ZipSeedCounts`: `crosswalk_rows`, `centroids`, `acs_rows`,
`oews_rows`, `rent_rows`, `zev_zip_rows`, `zev_county_rows`.

This replace deletes every `zcta_acs` row for 2024. The national extract does
not include mean commute (`S0801` is not in the table-based summary files),
so `mean_commute` is null after a seed load. The San Mateo demo file still
has 26.2 minutes for `94402`. Load that demo after the national seed if a
screen still needs the commute number. Do not expect the national file to
fill it.

## One ZIP, local inputs

```python
from dce.data.zip_local import load_zip_local

local = load_zip_local("94402", conn)
```

`ZipLocalError` means the ZIP is not 5 digits or is not in the crosswalk.
`load_zip_local` does not use the network.

| Field | Meaning |
|---|---|
| `geo` | Same `GeoContext` as `resolve_zip` |
| `county_name` | Census name, for example `San Mateo County` |
| `cbsa_name` | Division title when `geo.cbsa` is a division |
| `oews_area` | Parent CBSA that OEWS publishes. `41884` becomes `41860`. `00000` is the nation |
| `lat`, `lon` | 2024 Gazetteer internal point of `geo.zcta`. `None` if that vintage is missing |
| `land_sqmi` | `ALAND_SQMI` for the same point |
| `acs_year` | Newest stored ACS year, or `None` |
| `population`, `households` | ACS `B01003_001E`, `B11001_001E` |
| `median_hh_income` | `B19013_001E`. Census suppression is `None` |
| `median_gross_rent` | `B25064_001E`, dollars per month |
| `median_home_value` | `B25077_001E`. `2000001` is the Census top-code |
| `vehicles_available` | `B25046_001E` |
| `mean_commute` | `None` in the national seed. See above |
| `rent` | A `RentResolution`, or `None` when the chain cannot finish |
| `rent_error` | The `RentResolutionError` text when `rent` is `None` |
| `wages` | `OewsWageRecord` rows for `oews_area`. Falls back to area `00000` |
| `wage_basis` | `cbsa`, `national`, or `missing` |
| `ev` | A `ZipEvLocal` |

`94402` from this seed: population 25475, households 10125, income 172522,
median gross rent 3501, home value 2000001, vehicles 18262, internal point
37.540103, -122.330103, land 5.05 square miles.

### Wages

`oews_area_for_cbsa` in `dce.data.ingest.bls_oews` maps all 37 July 2023
metropolitan divisions, not only `41884`. The seed stores May 2025 annual
mean and median for SOC `49-3023` on 392 metropolitan parent CBSAs.
Guayama, PR (`25020`) had no annual series. Micropolitan ZIPs and ZIPs with
no CBSA use the national row.

Delivery-mix SOCs from `assumptions.yaml` are stored for the nation and for
`41860` only:

| SOC | Title in the seed |
|---|---|
| `41-2031` | Retail Salespersons |
| `53-7061` | Cleaners of Vehicles and Equipment |
| `53-7062` | Laborers and Freight, Stock, and Material Movers, Hand |
| `53-7065` | Stockers and Order Fillers |
| `41-1011` | First-Line Supervisors of Retail Sales Workers |
| `49-3023` | Automotive Service Technicians and Mechanics |

`OewsWageRecord.mean_annual` and `median_annual` are dollars per year.
`as_of` is `2025-05-01`. A `*` or `#` in the BLS file is `None`.

National May 2025 SOC `49-3023`: mean 56420, median 50620.
CBSA `41860`: mean 75730, median 76030.

### Vehicles

`ZipEvLocal` fields: `source`, `ev_proxy`, `as_of`, `bev`, `phev`, `fcev`,
`total_ldv`, `tesla_bev_sales`, `county_tesla_share`, `citation`.

- California, with CEC rows loaded: `source` is `cec`, `ev_proxy` is `None`.
  `bev` / `phev` / `fcev` sum the newest stored year's ZIP fuel rows
  (`Electric`, `PHEV`, `Hydrogen`). `tesla_bev_sales` is ZIP `Electric`
  times Tesla's share of `Electric` sales in the county. County names in the
  CEC file have no `County` suffix. `San Mateo County` matches `San Mateo`.
  The seed is calendar year 2026 from the workbook linked in
  `data/seed/coverage.json` (7,953 ZIP rows, 4,082 county rows).
- California, DMV row only: `source` is `dmv`. Tesla sales stay `None`.
- California, nothing stored: `source` is `missing`.
- Any other state: `source` is `fallback`, `ev_proxy` is
  `acs_national_fallback`, and the count fields are `None`. This does not
  invent a state Tesla total. When the caller has one, allocate it with
  `dce.data.ingest.zev_sales.allocate_state_tesla_volume` using the ZIP's
  households, income, and an EV share.

## Rent

```python
from dce.data.rent_resolver import resolve_rent

rent = resolve_rent("94402", conn)
```

`RentResolution` fields, unchanged: `zip_code`, `rent_psf_year`,
`rent_psf_month` (`rent_psf_year / 12`), `property_type`, `tier`,
`confidence`, `as_of`, `citation`. The same row is written to
`rent_resolved_cache`. `components_json` holds the inputs, including `tier`.

The chain, in order:

| Tier id | When | Confidence |
|---|---|---|
| `broker_county` | `rent_market` has a row for `geo.county_fips` (a borough or submarket). Used directly | `high`; `medium` for `office_showroom_proxy` |
| `cbsa_raw` | An industrial seed exists for `geo.cbsa` in `rent_cbsa`. The observed rate is used directly | `high` |
| `broker_cbsa` | `rent_market` has a row for `geo.cbsa`. Used directly | `high`; `medium` for `office_showroom_proxy` |
| `county_gsa` | No CBSA seed. County median of `rent_zip_obs` with `source = 'gsa'`. The ACS factor is applied only on this borrowed base | `medium` |
| `state` | Median of `rent_cbsa` industrial seeds in the state, and at least 3 distinct CBSA seeds. `rent_market` rows are not counted | `medium` |
| `national` | Industrial seed stored under CBSA `00000` | `low` |
| `hud_safmr` | Newest `rent_safmr` 2-bedroom monthly rent, converted | `low` |
| `acs_gross_rent` | This ZCTA's ACS `B25064` monthly rent, converted | `low` |
| `acs_gross_rent_county` | Median of ZCTA ACS gross rents in the dominant county | `low` |
| `acs_gross_rent_cbsa` | Median of ZCTA ACS gross rents in the CBSA | `low` |
| `acs_gross_rent_state` | Median of ZCTA ACS gross rents in the state | `low` |
| `acs_gross_rent_national` | Median of ZCTA ACS gross rents in the US | `low` |

`RentResolutionError` when the ZIP is missing from the crosswalk, or when the file has no ACS gross rent anywhere and none of the earlier rungs hit. The ZIP is on `.zip_code`.

The factor is model `acs_rent_v1`:

```
factor = (zcta_median_gross_rent / cbsa_median_of_zcta_gross_rents) ** b_acs_rent
```

Shipped exponents: `b_acs_rent = 1`, `b_income = b_density = b_home_value = 0`.
The factor is clamped to 0.5–2.0. The CBSA median uses ZCTAs whose own ZIP
code equals the ZCTA, so a PO box is not a second copy of the same rent.
Reference rents are the ZCTAs on that CBSA code, which is the division when
`geo.cbsa` is a division.

Residential conversion, used by `hud_safmr` and `acs_gross_rent`:

```
rent_psf_year = monthly * 12 / unit_sqft * commercial_residential_ratio
```

Shipped `unit_sqft` is 1000 and the ratio is 1, so this is a residential
proxy in dollars per square foot per year. `property_type` is
`residential_proxy`. It is not the Bay Area industrial headline.

The only `rent_cbsa` row is CBSA `41884`, $25.68 per square foot per
year ($2.14 per square foot per month), `as_of` 2026-09-30, Kidder Mathews
Peninsula Industrial Market Report Q3 2026. A ZIP in another state, and a
California ZIP in another CBSA, does not receive that number. One metro seed
is not enough for the state tier. There is no national industrial row, so
that tier does nothing until a curator adds CBSA `00000`.

`rent_market` holds the broker market-report rows from
`data/seed/rent_market.csv` (Cushman & Wakefield MarketBeat Q3 2026, 29
CBSAs and 21 counties). `rent_psf_year` there is already the annual NNN
equivalent: monthly figures × 12, full-service gross ÷ 1.15. The rent type,
unit rule, and coverage are in `docs/DATA_SOURCES.md` §8. `sync_rent_market`
rewrites the table when it differs from the bundled CSV, so a database
seeded by an older build picks up new rows on the next `estimate`.
`10001` resolves on `broker_county` 36061 (Manhattan office overall,
$74.37 full-service gross, $64.67 NNN). `78701` resolves on `broker_cbsa`
12420 (Austin office service/flex, $15.09 NNN).

`94402` resolves on `cbsa_raw` at the Kidder headline, $25.68 per square
foot per year. The ACS factor is not applied on top of that observed
submarket comp. A ZIP with no industrial seed and no rent of its own uses
the county, CBSA, state, or national ACS median and is marked as a fallback.

## Boundaries for MapLibre

Do not parse a national GeoJSON in the window. That file is 71,158,217
bytes and MapLibre would decode every polygon.

Use `data/geo/zcta_us.pmtiles` (gitignored, 22,151,345 bytes, built by
`make zcta-boundaries`). Vector tiles, layer name `zcta`, zooms 3 through 8,
one property `zcta` (the ZCTA code, which is the ZIP to pass to
`load_zip_local`). Every polygon is kept (`--no-feature-limit`). Coordinates
are EPSG:4326. The source is the 2020 cartographic ZCTA file at 1:500,000,
Douglas-Peucker simplified by 0.001 degrees (about 111 meters) with topology
preserved. `data/geo/boundary_build.json` is the committed record of those sizes. `scripts/build_zcta_boundaries.py` does not rewrite it unless `--record` is passed.

`data/geo/zcta_bay_area.geojson` is the committed fixture (452,598 bytes,
300 ZCTAs): the ZCTAs whose dominant county is one of Alameda, Contra Costa,
Marin, Napa, San Francisco, San Mateo, Santa Clara, Solano, and Sonoma. Same
simplification and the same `zcta` property. It is the offline sample, not
the nationwide click map.

Clicking a polygon passes `properties.zcta` to `load_zip_local`. Comparing
two ZIPs is two calls.

## What `estimate` reads

`estimate(zip)` calls `load_zip_local` after `resolve_zip`. Demand,
households, income, rent, and the OEWS wage come from that ZIP. The wage
is SOC 49-3023 mean annual pay for the ZIP's CBSA, or the national row
when the ZIP is micropolitan or non-metro. The hourly fallback is used
only when no OEWS row exists. SOC 49-3023 is the series stored for every
metro. It is not a delivery-role mix.

California origin demand is the ZIP's 2026 CEC battery-electric count
(the seed is Q1–Q3) times that county's Tesla share, times 4/3, times the
base handover factor 1.10. Outside California the seed has no state Tesla
total. The job allocates Cox/KBB 2025 US Tesla sales 589,160 minus the
CEC 2025 California Tesla total 169,650 by households and income. The
EV-share term is 1. A suppressed income uses the $80,000 reference.

Energy and demand charges come from the electricity ladder: a utility
tariff (PG&E Schedule B-10 on PG&E territory), then that utility's EIA-861
commercial average, then EIA Table 5.6.A for the state, then the U.S.
total. An average sets the demand charge to 0 because demand is already
in the $/kWh. Commercial property tax is the Lincoln Institute rate for
the county's studied city, or the state's studied city when the county is
not in the study, and it shifts the NNN load. Fit-out uses the BEA goods
price parity. `mean_commute` is null: ACS S0801 is not in the national
summary file.

`acs_rent_v1` still has zero income, density, and home-value exponents.
The ZIP adjustment is the ACS median gross rent ratio only, until a fit
against the GSA Lease Inventory exists. Those coefficients live in
`data/seed/rent_model_coeffs.json`.
