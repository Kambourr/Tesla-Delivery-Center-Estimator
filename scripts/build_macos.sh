#!/bin/bash
# Build the unsigned macOS arm64 .app. PyInstaller cannot cross-compile this stack.
#
#   ./scripts/build_macos.sh
#       PyInstaller only. Bundles data/results/dce.sqlite and the PMTiles
#       archive when those files are already on disk.
#
#   ./scripts/build_macos.sh --app-bundle
#       Full offline app. Runs make zip-inputs and make zcta-boundaries when
#       their outputs are missing, then the nationwide `dce precompute`
#       (no --sample, no --limit), then PyInstaller. Writes dist/app-report.json.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_BUNDLE=0
if [[ "${1:-}" == "--app-bundle" ]]; then
  APP_BUNDLE=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: scripts/build_macos.sh [--app-bundle]" >&2
  exit 2
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "scripts/build_macos.sh builds an arm64 .app and must run on macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "scripts/build_macos.sh targets Apple Silicon (arm64). This Mac is $(uname -m)." >&2
  exit 1
fi

PYTHON="${PYTHON:-python3}"
"${PYTHON}" -m pip install -e ".[packaging]"
RESULTS_DIR="data/results"
RESULTS_DB="${RESULTS_DIR}/dce.sqlite"

seed_ready() {
  local name
  for name in \
    zip_crosswalk.csv \
    zcta_acs_2024.csv \
    zcta_centroid_2024.csv \
    oews_metro_2025.csv \
    rent_cbsa.csv \
    zev_zip_sales.csv \
    coverage.json
  do
    if [[ ! -f "data/seed/${name}" ]]; then
      return 1
    fi
  done
}

if [[ "${APP_BUNDLE}" == "1" ]]; then
  if ! seed_ready; then
    make zip-inputs
  fi
  if [[ ! -f data/geo/zcta_us.pmtiles ]]; then
    make zcta-boundaries
  fi
  mkdir -p "${RESULTS_DIR}"
  PRECOMPUTE_STARTED=$("${PYTHON}" -c "import time; print(time.time())")
  # Nationwide. Do not pass --sample or --limit.
  "${PYTHON}" -m dce precompute --data-dir "${RESULTS_DIR}"
  PRECOMPUTE_FINISHED=$("${PYTHON}" -c "import time; print(time.time())")
  "${PYTHON}" - <<PY
import sqlite3
from pathlib import Path

path = Path("${RESULTS_DB}")
conn = sqlite3.connect(path)
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
conn.commit()
conn.close()
for suffix in ("-wal", "-shm"):
    extra = Path(str(path) + suffix)
    if extra.exists():
        extra.unlink()
PY
  export DCE_REQUIRE_RESULTS=1
  export DCE_PRECOMPUTE_STARTED="${PRECOMPUTE_STARTED}"
  export DCE_PRECOMPUTE_FINISHED="${PRECOMPUTE_FINISHED}"
fi

"${PYTHON}" -m PyInstaller --noconfirm --clean \
  --workpath build/pyinstaller \
  --distpath dist \
  packaging/dce_macos.spec

APP="dist/DeliveryCenterEstimator.app"
echo "Built ${APP}"
echo "Gatekeeper: right-click the app and choose Open the first time."

if [[ "${APP_BUNDLE}" == "1" ]]; then
  mkdir -p dist
  SMOKE_JSON="dist/smoke.json"
  BIN="${APP}/Contents/MacOS/DeliveryCenterEstimator"
  DCE_SMOKE_OUT="${PWD}/${SMOKE_JSON}" "${BIN}" --smoke
  DCE_APP_PATH="${APP}" \
    DCE_RESULTS_DB="${RESULTS_DB}" \
    DCE_SMOKE_JSON="${SMOKE_JSON}" \
    "${PYTHON}" - <<'PY'
import json
import os
from pathlib import Path

app = Path(os.environ["DCE_APP_PATH"])
db = Path(os.environ["DCE_RESULTS_DB"])
smoke = json.loads(Path(os.environ["DCE_SMOKE_JSON"]).read_text(encoding="utf-8"))
started = float(os.environ["DCE_PRECOMPUTE_STARTED"])
finished = float(os.environ["DCE_PRECOMPUTE_FINISHED"])
clicks = {}
for row in smoke.get("clicks", []):
    if isinstance(row, dict) and "zip" in row:
        clicks[str(row["zip"])] = row.get("click_ms")
report = {
    "app_path": str(app),
    "app_bytes": sum(path.stat().st_size for path in app.rglob("*") if path.is_file()),
    "results_db_bytes": db.stat().st_size,
    "precompute_seconds": finished - started,
    "rows": smoke.get("rows", {}),
    "cold_start_ms": smoke.get("cold_start_ms"),
    "click_ms": clicks,
    "opened_from": smoke.get("opened_from"),
    "smoke_ok": smoke.get("ok"),
}
out = Path("dist/app-report.json")
out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(out.read_text(encoding="utf-8"), end="")
if smoke.get("ok") is not True:
    raise SystemExit("Packaged smoke test failed. See dist/smoke.json.")
PY
fi
