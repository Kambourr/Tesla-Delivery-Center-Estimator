#!/bin/bash
# Build the unsigned macOS arm64 .app. PyInstaller cannot cross-compile this stack.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "scripts/build_macos.sh builds an arm64 .app and must run on macOS." >&2
  exit 1
fi
if [[ "$(uname -m)" != "arm64" ]]; then
  echo "scripts/build_macos.sh targets Apple Silicon (arm64). This Mac is $(uname -m)." >&2
  exit 1
fi

PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pip install -e ".[packaging]"
"$PYTHON" -m PyInstaller --noconfirm --clean packaging/dce_macos.spec
echo "Built dist/DeliveryCenterEstimator.app"
echo "Gatekeeper: right-click the app and choose Open the first time."
