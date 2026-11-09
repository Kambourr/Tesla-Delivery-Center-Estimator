# UI result contract

The map reads and writes JSON. Schema id: `dce.ui_result.v1`.

The page gets it from `AppApi.get_result(zip)`. A batch job can write the
same document ahead of time. Money is USD. Rates are fractions (`0.136` is
13.6%). ZIP codes are 5-character strings. `null` means the model returned
`None` (IRR or payback never crosses zero).

## Where a result is read

First hit wins:

1. The in-process cache, after this process has already produced or loaded
   the ZIP. The bridge then reports `source: "cache"`.
2. A precomputed document:
   - `DCE_UI_RESULTS_PATH` points at a JSON file or a directory.
     A file is either one result object or a map of ZIP to result object.
     A directory contains `{zip}.json` files, each one result object.
   - If that variable is unset and `<user data>/ui_results` already exists,
     it is used the same way. The app does not create it.
   - `dce.storage.repository.get_ui_result(zip_code)`, when that function
     exists. It should return the JSON text or the object, or `None`.
     The app does not open SQLite and does not run SQL. A missing function
     or a raised error is treated as "no row".
3. The on-disk cache `<user data>/ui_cache/{zip}.json`, written after a
   compute when the desktop app is running.
4. A compute, on a worker thread named `dce-ui_*`. The bridge reports
   `source: "computed"` the first time and caches the object.

A precomputed object is used only when `schema` is `dce.ui_result.v1` and
`zip_code` matches the request. Anything else is ignored and the ZIP is
computed.

The user-data directory is the one in ADR-0002 (`dce.config.user_data_dir`).

## Suggested storage table

Not created by this package. When the batch job lands, this is the shape
`get_ui_result` should read:

```sql
CREATE TABLE ui_result (
  zip_code TEXT PRIMARY KEY,
  schema TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  computed_at TEXT NOT NULL
);
```

`payload_json` is one `dce.ui_result.v1` object. `get_ui_result(zip_code)`
returns that text, or `None` when the ZIP is absent.

## Result object

```json
{
  "schema": "dce.ui_result.v1",
  "zip_code": "94402",
  "source": "computed",
  "computed_at": "2026-11-09T19:00:00+00:00",
  "geo": {
    "zip_code": "94402",
    "zcta": "94402",
    "county_fips": "06081",
    "cbsa": "41884",
    "state": "CA"
  },
  "centroid": {"lat": 37.56, "lon": -122.32},
  "cost_per_delivery": 500.94,
  "annualized_total_cost": 2767000.0,
  "estimated_annual_deliveries": 5522.8,
  "components": {"lease": 0, "labor": 0, "utilities": 0, "property_tax": 0, "capex": 0, "other_opex": 0},
  "drivers": [
    {"name": "labor", "label": "Labor", "usd": 0, "share": 0.5}
  ],
  "catchment": {
    "beta": 2.0,
    "gravity": {
      "method": "gravity",
      "beta": 2.0,
      "deliveries_per_year": 5522.8,
      "zips": [{"zip_code": "94402", "deliveries_per_year": 100.0, "share": 0.4}],
      "taken_from": [{"center_id": "colma", "name": "Tesla Delivery Colma", "deliveries_per_year": 2000.0}]
    },
    "nearest": {"method": "nearest", "beta": null, "deliveries_per_year": 4370.0, "zips": [], "taken_from": []}
  },
  "dcf": {
    "standalone": {"benefit_mode": "standalone", "discount_rate": 0.136, "npv": 0, "irr": 0.86, "simple_payback_years": 1.31, "discounted_payback_years": 1.51, "total_capex": 3780000, "terminal_value": 0, "years": []},
    "incremental": {"benefit_mode": "incremental", "discount_rate": 0.136, "npv": 0, "irr": null, "simple_payback_years": null, "discounted_payback_years": null, "total_capex": 3780000, "terminal_value": 0, "years": []}
  },
  "scenarios": {
    "low": {"scenario_id": "low", "label": "Low (bad outcome)", "cost_per_delivery": 0, "annual_deliveries": 0, "annualized_total_cost": 0, "standalone": {"npv": 0, "irr": null, "simple_payback_years": null, "discounted_payback_years": null, "discount_rate": 0.163}, "incremental": {"npv": 0, "irr": null, "simple_payback_years": null, "discounted_payback_years": null, "discount_rate": 0.163}},
    "base": {},
    "high": {}
  },
  "tornado": [
    {"driver": "deliveries", "label": "Deliveries", "unit": "deliveries/yr", "input_base": 0, "input_at_npv_low": 0, "input_at_npv_high": 0, "npv_low": 0, "npv_base": 0, "npv_high": 0, "swing": 0}
  ],
  "nearby_centers": [
    {"center_id": "colma", "name": "Tesla Delivery Colma", "city": "Colma", "state": "CA", "distance_miles": 12.2, "lat": 37.69, "lon": -122.45, "deliveries_taken": 2000.0}
  ]
}
```

`base` and `high` use the same fields as `low`. Scenario ids are exactly
`low`, `base`, and `high` (`dce.scenarios.outcome_scenarios`). The headline
DCF is the unshocked gravity case, the same one `estimate(zip)` returns.
`scenarios.base` is that case with the base DCF knobs written out explicitly.
They should match the headline NPV within a dollar.

`drivers` is the top three annualized cost components, largest first, ties
by name. `share` is that component's share of the annualized total.

`catchment.gravity` is the base allocation and the one the map highlights.
`catchment.nearest` is the low case. `zips` are only the ZIPs with a
positive share. The map paints `share` as the fill. A ZIP with no polygon
in the loaded GeoJSON is skipped on the map and still listed in the JSON.

`dcf.standalone.years` and `dcf.incremental.years` each have 11 rows, year 0
through year 10. Year fields are `year`, `deliveries`, `headcount`,
`benefit`, `lease`, `labor`, `utilities`, `property_tax`, `other_opex`,
`opex`, `ebitda`, `capex`, `fed_depreciation`, `state_depreciation`, `tax`,
`fcf`, `discounted_fcf`, `cumulative_fcf`, `cumulative_discounted_fcf`.
Scenario cards do not repeat the yearly tables.

`tornado` is the standalone NPV tornado from `dcf_tornado`, largest `swing`
first. The page draws an SVG of these numbers. It does not recompute them.

`nearby_centers` is the five closest delivery centers and hubs by
straight-line miles from the candidate centroid. `deliveries_taken` is the
gravity volume taken from that center, or `null` when the catchment did not
take any.

`source` inside the object is `computed` or `precomputed`. The bridge
envelope is separate and may say `cache`.

## Bridge envelopes

Success:

```json
{"ok": true, "source": "computed", "result": {}}
```

`source` is `computed`, `precomputed`, or `cache`.

Failure, not cached:

```json
{"ok": false, "error": {"code": "unknown_zip", "message": "ZIP 00000 is not in the local HUD crosswalk fixture (M1 includes 94401-94404)."}}
```

`code` is `invalid_zip`, `unknown_zip`, `estimate_failed`, or `map_failed`.

## Compare

`AppApi.compare(zip_a, zip_b)` returns `dce.ui_compare.v1`:

```json
{
  "ok": true,
  "schema": "dce.ui_compare.v1",
  "a": {},
  "b": {},
  "metrics": [
    {
      "id": "cost_per_delivery",
      "label": "Cost / delivery",
      "better": "lower",
      "format": "usd",
      "a": 501,
      "b": 640,
      "winner": "a"
    }
  ]
}
```

`a` and `b` are result objects. `winner` is `a`, `b`, or `tie`. A `null`
IRR or payback loses to a number, because `null` means it never pays back.
Equal numbers within `1e-6` absolute or `1e-9` relative are a tie.

| id | better | format |
|---|---|---|
| `cost_per_delivery` | lower | `usd` |
| `estimated_annual_deliveries` | higher | `count` |
| `standalone_npv` | higher | `usd` |
| `standalone_irr` | higher | `ratio` |
| `standalone_simple_payback_years` | lower | `years` |
| `standalone_discounted_payback_years` | lower | `years` |
| `incremental_npv` | higher | `usd` |
| `incremental_irr` | higher | `ratio` |
| `incremental_simple_payback_years` | lower | `years` |
| `incremental_discounted_payback_years` | lower | `years` |

`format` tells the page how to render the number. `ratio` is a fraction.
`usd` is dollars, and the page may shorten millions.

The two ZIPs must differ. The bridge computes them in parallel when both
are cold.

## Map payload

`bootstrap()` returns `dce.ui_map.v1`:

```json
{
  "ok": true,
  "schema": "dce.ui_map.v1",
  "zcta": {"type": "FeatureCollection", "features": []},
  "zip_index": [{"zip": "94402", "lat": 37.56, "lon": -122.32}],
  "centers": [
    {"center_id": "colma", "name": "Tesla Delivery Colma", "city": "Colma", "state": "CA", "zip_code": "94014", "lat": 37.69, "lon": -122.45, "location_type": "delivery"}
  ],
  "basemap_style": "vendor/basemap-style.json",
  "zcta_name": "bay_area_zcta.geojson"
}
```

### ZCTA GeoJSON

`DCE_ZCTA_GEOJSON` replaces the shipped Bay Area fixture. The file is a
GeoJSON FeatureCollection. Each polygon's ZIP is the first of these
properties that is a 5-digit string: `zip`, `zcta`, `ZCTA5CE20`,
`ZCTA5CE10`, `GEOID20`, `GEOID10`. The app rewrites that to
`properties.zip` and sets the feature id to the same string so hover and
selection can use MapLibre feature-state.

`properties.lat` and `properties.lon` are optional. When they are missing,
the search box uses the average of the polygon's coordinates.

The national extract should keep this property name (or one of the Census
names above) and be pointed at with `DCE_ZCTA_GEOJSON`. The app does not
need a code change to switch files.

### Centers

Markers are rows from the US delivery-center snapshot whose
`location_type` is `delivery` or `hub`. Other location types are left off
the map so stores and service sites do not read as delivery centers.

### Basemap

`basemap_style` is a URL or a path relative to the page. The default,
`vendor/basemap-style.json`, is bundled. `DCE_BASEMAP_STYLE` replaces it
with another MapLibre style document. Tiles and glyphs in the default style
are requested from OpenFreeMap at runtime. They are allowed to fail. The
page then shows the note "Basemap tiles are offline" and still draws the
ZIP layer and the markers.

## Page behavior the JSON has to support

- Clicking a ZIP replaces the dashboard. A newer click discards a slower
  response for the previous ZIP.
- While `get_result` is in flight the panel is a skeleton.
- The gravity ZIP list is the catchment highlight.
- Compare mode shows the metric rows above, with `winner` drawn brighter.
- The search box jumps to a ZIP in `zip_index` and selects it. A 5-digit
  ZIP that is not in the index is still sent to `get_result`; the map has
  no polygon to highlight until the shapes include it.
