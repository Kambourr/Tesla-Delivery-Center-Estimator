# Data Dictionary (logical)

## Inputs (user)

The only required input is `zip_code`. Everything else is an assumption default, a scenario preset, or an optional advanced override. Rent is resolved by `resolve_rent` (see DATA_SOURCES §8) and is not a required field.

| Field | Type | Notes |
|---|---|---|
| `zip_code` | char(5) | US ZIP; leading zeros preserved as text. **Required.** |
| `rent_psf_month` | float? | Optional advanced override only. Absent → rent resolver. Never required. |
| `sqft` | float | Assumption default 25000, not typed each run |
| `vehicle_mix` | map[str,float] | Scenario preset; shares sum to 1 |
| `wage_shock` | float | Scenario preset: −0.2, 0, +0.2 |
| `catchment_miles` | float | Assumption default 15 |

## Core outputs

| Field | Type | Notes |
|---|---|---|
| `cost_per_delivery` | float | USD |
| `annualized_total_cost` | float | USD / year |
| `estimated_annual_deliveries` | float | Units / year |
| `drivers` | list[{name, usd, share}] | Top 3 |
| `scenario_id` | str | e.g. `base`, `wage_p20`, `mix_alt` |
| `spearman_drivers` | float | vs baseline driver ranks |
| `spearman_zips` | float? | When batch comparing ZIPs |
| `map_path` | path | Folium HTML |
| `staleness` | list[{source, as_of, status}] | UI badges |

## Cost components (`name` keys)

`lease`, `labor`, `utilities`, `property_tax`, `capex`, `other_opex`

## SQLite essentials

### source_registry
`source_id PK`, `url`, `as_of TEXT ISO`, `fetched_at`, `ttl_days INT`, `license_note`, `bytes INT`

### zcta_acs
`zcta TEXT`, `year INT`, `population`, `median_hh_income`, `vehicles_available`, `mean_commute`, `median_home_value`, `PRIMARY KEY(zcta,year)`

`median_home_value` is ACS `B25077_001E`. Schema version 2 adds the column. `2000001` is the Census top-code for $2,000,000 or more.

### oews_wage
`area_code`, `area_name`, `soc`, `soc_title`, `mean_annual`, `median_annual`, `as_of`

### ev_zip
`zip`, `state`, `bev`, `phev`, `fcev`, `total_ldv`, `as_of`, `source` (`cec`|`dmv`|`fallback`)

### utility_rate
`utility_id`, `schedule`, `geography`, `energy_rate_kwh`, `demand_rate_kw`, `as_of`, `source` (`pge_pdf`|`eia`|`openei`)

### rent_default
Logical summary kept for early milestones: `geo_key` (CBSA or county), `rent_psf_month`, `citation`, `as_of`, `confidence` (`high`|`medium`|`low`|`fmr_weak`).

The physical rent tables (bundled seed + resolver cache) are `rent_cbsa`, `rent_zip_obs`, `rent_model_coeffs`, and `rent_resolved_cache` in DATA_SOURCES §8. M1 may create `rent_default`; the rent milestone creates the physical tables. Resolved rent is automatic. `confidence=low` is the HUD SAFMR / ZORI proxy tier.

### extract_cache
`pdf_sha256 PK`, `extractor` (`manual`|`llm`), `json TEXT`, `created_at`
