# Building the macOS app

The desktop app is an unsigned Apple Silicon `.app`. It opens a pywebview
window (WKWebView) on the local MapLibre page. The nationwide ZIP results,
the PMTiles boundaries, MapLibre, the PMTiles protocol, and the seeds are
inside the bundle. After the first launch the map works with no network.
There is no CDN script. If the OpenFreeMap basemap cannot be reached, the
page switches to the bundled dark style (`vendor/basemap-offline.json`) and
keeps the ZIP polygons and center markers on that background.

PyInstaller cannot cross-compile this stack. Build on an Apple Silicon Mac.
`make build` and `make app-bundle` exit 1 on any other machine.

## `make app-bundle`

This is the offline app. It does not pass `--sample` or `--limit`.

1. `make zip-inputs` when a nationwide seed file is missing.
2. `make zcta-boundaries` when `data/geo/zcta_us.pmtiles` is missing.
   That target downloads the Census 2020 cartographic ZCTA file if the
   cache at `/tmp/dce-public` does not already have it, and it needs
   `tippecanoe` on `PATH`.
3. `dce precompute --data-dir data/results` for every resolvable US ZIP.
   The job is resumable. A second run leaves fresh rows in place.
4. Checkpoint the SQLite file so the bundle is one database, not a WAL pair.
5. PyInstaller (`packaging/dce_macos.spec`) writes
   `dist/DeliveryCenterEstimator.app`.

`make build` is PyInstaller only. It bundles a results database and a
PMTiles archive when those files are already on disk. It does not run the
precompute.

Install once, then build:

```bash
brew install tippecanoe
python3 -m pip install -e ".[packaging]"
make app-bundle
```

The script installs the `packaging` extra again so a clean shell still has
PyInstaller. When `PYTHON` is unset it uses `.venv/bin/python` if that file
is executable, and otherwise `python3`. It clears the macOS hidden flag on
the venv's `.pth` files and puts `src` on `PYTHONPATH`, because Python 3.14
skips a hidden `.pth` and then cannot import the editable install. After
PyInstaller it strips extended attributes from the bundle (`xattr -cr`) and
signs it ad hoc (`codesign --force --deep -s -`), then checks that signature
with `codesign --verify --deep --strict`. Gatekeeper: right-click
`dist/DeliveryCenterEstimator.app` and choose Open the first time. The app
is not notarized and this repo does not create a release.

## What is inside the app

| Piece | Where it is read |
|---|---|
| Map page, MapLibre GL JS 4.7.1, PMTiles, both basemap styles | `dce/app/web` inside the bundle |
| Seeds, assumptions, San Mateo demo rates | `data/seed`, `data/defaults`, `data/demo` |
| Bay Area GeoJSON, and `zcta_us.pmtiles` when it was built | `data/geo` |
| Schema | `dce/storage/schema.sql` |
| Precomputed `dce.sqlite` | `data/results/dce.sqlite` |

The results database is opened read-only. SQLite is asked for `mode=ro` and
`immutable=1`, so a launch does not write a journal next to the file in
`sys._MEIPASS`. If that open fails, the first launch copies the file to
`~/Library/Application Support/DCE/dce.sqlite` and opens the copy read-only.
That directory is only the packaged results file. A checkout still uses the
ADR-0002 directory, `~/Library/Application Support/DeliveryCenterEstimator/`.

Clicks read `zip_result` through `get_zip_result`. The stored document is
`dce.ui_result.v1`. A missing or error row is computed on a worker, the same
way a checkout computes a ZIP that was not precomputed.

## Smoke test

The frozen binary accepts `--smoke` and does not open a window:

```bash
dist/DeliveryCenterEstimator.app/Contents/MacOS/DeliveryCenterEstimator --smoke
```

It resolves 94402 and 78701 from the bundled database and prints JSON with
`cold_start_ms`, per-ZIP `click_ms`, and `rows` (`ok` and `error`). Set
`DCE_SMOKE_OUT` to also write that JSON to a file.

`tests/packaging/test_frozen_app.py` launches that binary and checks both
payloads against `estimate()` from the source tree (cost, deliveries, geo,
both DCF lenses, catchment totals, and driver names). The test skips when
no `.app` is present, so the regular CI job stays a unit-test run. The
macOS workflow sets `DCE_REQUIRE_FROZEN=1` and fails if the binary is missing.

## GitHub Actions

`.github/workflows/macos-app.yml` is separate from `.github/workflows/ci.yml`.
It runs on `workflow_dispatch` and on tag pushes, on `macos-latest` (arm64).
It runs `make app-bundle`, the packaged smoke test, and uploads two
artifacts: `DeliveryCenterEstimator-macos-arm64.zip` and `dist/app-report.json`.
It does not create a GitHub Release and it does not publish the app.

`dist/app-report.json` records:

- `app_bytes`, the size of the `.app`
- `precompute_seconds`, the nationwide precompute on that runner
- `rows.ok` and `rows.error`
- `cold_start_ms` and `click_ms` for 94402 and 78701

The workflow prints the same fields in the job summary.

## Report from a machine that is not an Apple Silicon Mac

`make app-bundle` exits before the precompute on Linux and on Intel Macs.
The `.app` size, the runner's precompute time, the nationwide row counts,
and the frozen cold-start and click times are produced by the macOS
workflow, not by a Linux checkout.
