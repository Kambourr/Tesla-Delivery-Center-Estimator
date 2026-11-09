# Tesla Delivery-Center Estimator

Desktop app that answers: **what if Tesla opens a delivery center in ZIP X?**

It will estimate cost per delivery, the top three cost drivers, and a customer-base map. It uses **public data only**. It never uses Tesla internal data, and it never scrapes LoopNet or Crexi.

**Status:** milestone M0 (repository skeleton). The CLI is a stub. There is no cost model, GUI, data fetch, or seed database yet.

## Locked decisions

- **GUI:** Tkinter. The Folium map HTML opens in the system browser.
- **Package:** macOS Apple Silicon `.app` via PyInstaller. A Windows EXE is an optional later target.
- **Input:** a US ZIP resolves rent and every other input. Rent is not a required field. An optional advanced override may be added later.
- **Data:** a bundled SQLite seed so the first launch works offline, plus a per-source refresh cadence and staleness flags.
- **Math:** deterministic. An LLM API is allowed only in `dce.extract.pdf_llm`, never on the calculation path.

The spec lives in [`docs/`](docs/).

## Quickstart

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m dce --help
pytest
```

`pip install -e .` installs the package without pytest. Use the `dev` extra to run tests.

Copy `.env.example` to `.env` only when a later milestone calls Census, BLS, EIA, or HUD. M0 does not read `.env` and does not make network calls.

Tkinter is in the Python standard library (it is not a pip dependency). On Debian or Ubuntu, install the `python3-tk` system package before the GUI milestone. The M0 GUI module does not import Tkinter, so headless test runs do not need it.

## CI

GitHub Actions (`.github/workflows/ci.yml`) installs the package and runs `pytest` plus `python -m dce --help` on `macos-latest` and `ubuntu-latest`. The workflow has no secrets and does not build the `.app`.

## Layout

See [`docs/REPO_STRUCTURE.md`](docs/REPO_STRUCTURE.md).
