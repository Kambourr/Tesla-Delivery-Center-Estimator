# Precomputed ZIP results

`dce precompute` estimates every resolvable US ZIP and stores one row so a
map click does not recompute. The successful payload is a
`dce.ui_result.v1` document, the same shape `dce.app.results.build_ui_result`
returns. `docs/contracts/ui_results.md` is the field list. This page is the
table, the read API, and the fields this job adds.

The calculation is ordinary Python. Nothing on this path calls an LLM or
any other model API. The same inputs produce the same JSON bytes: keys are
sorted, `computed_at` is the input vintage `2026-11-09T00:00:00+00:00`
rather than the clock, and elapsed time stays in a column, not in the
document.

## Table

Schema migration version 6. The only SQL is in `dce.storage`.

`zip_result`

| column | meaning |
|---|---|
| `zip` | Primary key. Five characters. |
| `model_version` | Code constant `dce.precompute.MODEL_VERSION`. |
| `inputs_hash` | sha256 of that version plus the public files listed below. |
| `status` | `ok` or `error`. |
| `reason` | Set on an error row. Null on success. |
| `payload_json` | Canonical JSON of the document. |
| `computed_at` | The same vintage timestamp as the document. |
| `elapsed_ms` | Wall time for that ZIP. Not part of the document, so a rerun can differ here. |

Index `zip_result_fresh` is `(model_version, inputs_hash, status)`.

A row is fresh when both `model_version` and `inputs_hash` match the
process that is reading. A fresh `ok` row and, unless `--retry-errors` is
set, a fresh `error` row are left in place. Anything else is estimated
again.

`inputs_hash` covers `MODEL_VERSION`, `data/defaults/assumptions.yaml`,
`data/demo/san_mateo/operating_inputs.json` (the utility-rate fallback),
and these seed files: `coverage.json`, `zev_zip_sales.csv`,
`zev_county_sales.csv`, `zcta_acs_2024.csv`, `zcta_centroid_2024.csv`,
`zip_crosswalk.csv`, `oews_metro_2025.csv`, `rent_cbsa.csv`,
`rent_model_coeffs.json`.

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
then sets:

| field | value |
|---|---|
| `source` | `precomputed` |
| `computed_at` | `2026-11-09T00:00:00+00:00` |
| `model_version` | `MODEL_VERSION` |
| `inputs_hash` | `inputs_hash()` |
| `provenance` | One object per resolved input. The map ignores this list. |

`scenarios.base` uses the ZIP's own rent, wage, and the PG&E B-10 fallback
rates, the same prices as the headline `estimate(zip)`. Its standalone NPV
matches the headline within a dollar. Scenario cards do not repeat the
yearly tables. Those 11 rows (year 0 through year 10) are on
`dcf.standalone.years` and `dcf.incremental.years`.

`provenance` objects are `name`, `value`, `unit`, `source`,
`geography_level`, `geography_id`, `fallback`, `detail`. `value` is the
number before scenario shocks, or `null` when the field is missing.
`geography_level` is `zip`, `zcta`, `county`, `cbsa`, `state`, `national`,
or `demo`. Names: `rent_psf_month`, `wage_annual`, `energy_rate_kwh`,
`demand_rate_kw`, `population`, `households`, `median_hh_income`,
`median_gross_rent`, `median_home_value`, `vehicles_available`,
`mean_commute`, `zip_origin_deliveries`, `handover_factor`,
`demand_annualization`, `catchment_deliveries`.

The headline deliveries, cost, catchment, and both DCF views are the base
outcome, which is what `estimate(zip)` returns.

## Error document

A ZIP that cannot be estimated is stored, not raised out of the batch.

```json
{
  "zip_code": "01093",
  "status": "error",
  "reason": "EstimateDataError: ZIP 01093 has no industrial seed, no SAFMR, and no ACS median gross rent.",
  "model_version": "2026.11.3-local-inputs",
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

A ZIP with no centroid, no rent, or no deliveries inside 60 miles becomes
an error row. The batch continues.
