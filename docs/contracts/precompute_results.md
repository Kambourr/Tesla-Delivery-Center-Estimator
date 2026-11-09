# Precomputed ZIP results

`dce precompute` estimates every resolvable US ZIP and stores one row so a
map click does not recompute. The successful payload is a
`dce.ui_result.v1` document from `dce.app.results.build_ui_result`, then
trimmed to the numbers the dashboard and the map paint. `estimate(zip)`
still returns the full catchment, the full year rows, and provenance.
`docs/contracts/ui_results.md` is the field list. This page is the table,
the read API, and the fields this job adds.

The calculation is ordinary Python. Nothing on this path calls an LLM or
any other model API. The same inputs produce the same JSON bytes: keys are
sorted, `computed_at` is the input vintage `2026-11-09T00:00:00+00:00`
rather than the clock, and elapsed time stays in a column, not in the
document.

## Table

Schema migration version 7. The only SQL is in `dce.storage`. Version 6
created `zip_result` with `payload_json` as text. Version 7 stores that
column as a BLOB. New rows are zlib level 9 of the canonical JSON.
`dce.storage.repository` expands the BLOB on read, and it still accepts a
plain JSON document copied forward from version 6. The results file is
created with a 512-byte page, then checkpointed and vacuumed, so the unused
tail of each overflow page stays small.

`zip_result`

| column | meaning |
|---|---|
| `zip` | Primary key. Five characters. |
| `model_version` | Code constant `dce.precompute.MODEL_VERSION`. |
| `inputs_hash` | sha256 of that version plus the public files listed below. |
| `status` | `ok` or `error`. |
| `reason` | Set on an error row. Null on success. |
| `payload_json` | zlib of the canonical JSON. The read API returns the JSON text. |
| `computed_at` | The same vintage timestamp as the document. |
| `elapsed_ms` | Wall time for that ZIP. Not part of the document, so a rerun can differ here. |

Index `zip_result_fresh` is `(model_version, inputs_hash, status)`.

A row is fresh when both `model_version` and `inputs_hash` match the
process that is reading. A fresh `ok` row and, unless `--retry-errors` is
set, a fresh `error` row are left in place. Anything else is estimated
again.

`inputs_hash` covers `MODEL_VERSION`, `data/defaults/assumptions.yaml`,
`data/demo/san_mateo/operating_inputs.json`, and these seed files:
`coverage.json`, `zev_zip_sales.csv`, `zev_county_sales.csv`,
`zcta_acs_2024.csv`, `zcta_centroid_2024.csv`, `zip_crosswalk.csv`,
`oews_metro_2025.csv`, `rent_cbsa.csv`, `rent_market.csv`, `rent_model_coeffs.json`,
`electricity_commercial.csv`, `county_utility.csv`,
`property_tax_commercial.csv`, `bea_rpp_2024.csv`,
`construction_cost_factor.csv`.

## Read API

```python
def get_zip_result(zip_code: str, *, data_dir: Path | None = None) -> dict | None: ...
def get_zip_results(zip_codes: Sequence[str], *, data_dir: Path | None = None) -> dict[str, dict]: ...
```

`get_zip_result` returns the stored document, or `None` when that ZIP has
no row. `get_zip_results` returns the ZIPs that have a row, in request
order. Both add `current: true` when the stored version and hash match
this process. They do not estimate.

`dce.app.precomputed.lookup_zip_result` calls `get_zip_result(zip)` with
no database argument, then `get_zip_results([zip])`. The desktop app keeps
the object only when `schema` is `dce.ui_result.v1` and `zip_code` matches.
An error document is a miss, and the app computes the ZIP itself.

## Success document

`build_ui_result(zip, source="precomputed")` builds the body. The batch
then sets `model_version` and `inputs_hash` and stores a compact copy:

`model_version`, `inputs_hash`, and `computed_at` are columns on
`zip_result`. They are not repeated in the JSON. `get_zip_result` and
`get_zip_results` copy them onto the document they return, along with
`current`.

| field | value on the document the read API returns |
|---|---|
| `source` | `precomputed` |
| `computed_at` | the `computed_at` column, `2026-11-09T00:00:00+00:00` |
| `model_version` | the `model_version` column |
| `inputs_hash` | the `inputs_hash` column |

The stored copy drops `provenance`. Gravity ZIPs keep `zip_code` and `share`
only. The nearest-center ZIP list is omitted. The nearest total stays.
`taken_from` keeps the first 8 centers, largest first, and folds the rest
into one row (`center_id` `other`, `name` `Other centers`,
`deliveries_per_year` the sum of the tail). Each DCF year row keeps `year`,
`deliveries`, `benefit`, `opex`, `fcf`, and `cumulative_fcf`. Each tornado
bar keeps `driver`, `label`, `npv_low`, `npv_base`, `npv_high`, and `swing`.
Each scenario card keeps `scenario_id`, `label`, `cost_per_delivery`, and
`standalone.npv` / `standalone.irr`. Headline cost, deliveries, drivers,
nearby centers (including `deliveries_taken`, which is summed from the full
`taken_from` before the trim), and gravity shares are the same numbers the
page prints.

`scenarios.base` uses the ZIP's own rent, wage, electricity, NNN load, and
fit-out index, the same prices as the headline `estimate(zip)`. Its standalone NPV
matches the headline within a dollar. Scenario cards do not repeat the
yearly tables. Those 11 rows (year 0 through year 10) are on
`dcf.standalone.years` and `dcf.incremental.years`.

`estimate(zip)` still carries `provenance`. Those objects are `name`,
`value`, `unit`, `source`, `geography_level`, `geography_id`, `fallback`,
`detail`. `value` is the number before scenario shocks, or `null` when the
field is missing. The stored row does not include them.
`geography_level` is `zip`, `zcta`, `county`, `cbsa`, `state`, `national`,
`utility`, or `demo`. Names: `rent_psf_month`, `wage_annual`, `energy_rate_kwh`,
`demand_rate_kw`, `property_tax_rate`, `opex_load`, `fitout_index`,
`status_quo_rent_psf_month`, `population`, `households`, `median_hh_income`,
`median_gross_rent`, `median_home_value`, `vehicles_available`,
`mean_commute`, `zip_origin_deliveries`, `handover_factor`,
`demand_annualization`, `catchment_deliveries`.

`property_tax_rate` has source `lincoln_mcfe_2024`: the commercial-class
rate on real property, at `county`, `cbsa` (a studied city in the same
metro and state), `state`, or `national`. `fitout_index` has source
`dod_ufs_3_701_01_2026` (DoD construction area cost factor) at `county`,
`cbsa`, `state`, or `national`, or `bea_rpp_goods_2024` when the DoD table
has no row for the place. `rent_psf_month` tries the broker rows first:
`broker_county` (county), Kidder `cbsa_raw` (CBSA 41884), then
`broker_cbsa`, before the ACS rungs. On
`2026.11.8-broker-rents-commercial-tax-acf` these broker rents, the
real-property tax rate, and the DoD fit-out factor apply together.
Field names and the document shape are unchanged from earlier
`dce.ui_result.v1` documents; only the values and `model_version`
differ, so rows from `2026.11.7-broker-rents` are stale.

The headline deliveries, cost, catchment, and both DCF views are the base
outcome, which is what `estimate(zip)` returns.

## Error document

A ZIP that cannot be estimated is stored, not raised out of the batch.
A missing rent on the ZIP itself is not an error: the resolver uses the
county, CBSA, state, or national median of ACS gross rent and marks that
rung as a fallback. A ZIP whose 60-mile catchment has no deliveries gets
an isolated origin (see `docs/MODULE_CONTRACTS.md`) and is stored as `ok`.
The example below is a ZIP that still cannot be estimated, such as one
with no Gazetteer centroid.

```json
{
  "zip_code": "00000",
  "status": "error",
  "reason": "EstimateDataError: ZIP 00000 has no 2024 Gazetteer internal point for ZCTA 00000.",
  "model_version": "2026.11.9-compact-results",
  "inputs_hash": "<sha256>",
  "computed_at": "2026-11-09T00:00:00+00:00"
}
```

There is no `schema` field, so the map treats it as no row.

## Command

```text
dce precompute [--sample bay-area] [--limit N] [--workers N] [--retry-errors] [--data-dir DIR]
```

No `--sample` estimates every ZIP `resolve_zip` can name that also has a
crosswalk row in the demand index (41,034 on this seed). `--sample bay-area`
keeps the nine Bay Area counties. `--limit` stops after that many of the
selected ZIPs. `--workers` defaults to 1 below 32 pending ZIPs and otherwise
to the CPU count, capped by the pending count. Workers are spawned, not
forked. The parent writes SQLite. `make precompute` is the Bay Area sample.

A ZIP with no centroid becomes an error row. A missing rent, and a ZIP
whose catchment is empty until the isolated-origin rung, do not. The batch
continues.
