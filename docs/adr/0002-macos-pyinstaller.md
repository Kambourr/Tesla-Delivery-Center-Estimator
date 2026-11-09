# ADR-0002: macOS-first PyInstaller app

- Status: accepted
- Date: 2026-11-09

## Context

The demo runs on Jacob's Apple Silicon Mac. PyInstaller has to run on the
same OS family as the artifact. geopandas and shapely wheels are not
cross-compiled from Linux into a Mac `.app` or a Windows EXE. Codesign and
notarization cost more than this class project should spend.

## Decision

The primary artifact is an unsigned macOS `arm64` `.app` built with
PyInstaller (`packaging/dce_macos.spec`, `scripts/build_macos.sh`). CI for
M0 runs tests on `macos-latest` and `ubuntu-latest`. It does not build the
app and it has no secrets. A Windows EXE is optional and later, and only
from a Windows runner (`packaging/dce.spec`).

The bundle includes `data/seed` so the first launch works offline. Document
right-click → Open for Gatekeeper.

## Consequences

- `make build` calls the macOS script. Until packaging is implemented, that
  script exits 1.
- Do not claim a Linux-built EXE or `.app` works.
- User data lives in `~/Library/Application Support/DeliveryCenterEstimator/`
  on macOS, `%LOCALAPPDATA%\DeliveryCenterEstimator\` on Windows, and
  `~/.local/share/delivery-center-estimator/` on Linux.
