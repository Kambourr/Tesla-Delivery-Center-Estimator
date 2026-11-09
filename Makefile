# Developer tasks. Prefer the project venv when it exists.
ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python3
endif

.PHONY: setup lint typecheck test build check app app-bundle zip-inputs zcta-boundaries precompute

setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e ".[dev]"
	.venv/bin/pre-commit install

lint:
	$(PYTHON) -m ruff check src tests scripts packaging
	$(PYTHON) -m ruff format --check src tests scripts packaging

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

# macOS arm64 .app. The script exits 1 on any other OS.
# PyInstaller only. Use app-bundle for the nationwide offline app.
build:
	./scripts/build_macos.sh

# Seeds if needed, nationwide boundaries if needed, full `dce precompute`, then the .app.
# No --sample and no --limit. The script exits 1 on any OS other than macOS arm64.
app-bundle:
	./scripts/build_macos.sh --app-bundle

# Open the pywebview map. Needs a display.
app:
	$(PYTHON) -m dce.app

check: lint typecheck test

# Public-data extracts. Not part of CI. See docs/DATA_SOURCES.md.
zip-inputs:
	$(PYTHON) scripts/build_zip_inputs.py --cache /tmp/dce-public --fetch-bls --fetch-zev

zcta-boundaries:
	$(PYTHON) scripts/build_zcta_boundaries.py --cache /tmp/dce-public --download

# Nine Bay Area counties. The full nation is `dce precompute` with no --sample.
precompute:
	$(PYTHON) -m dce precompute --sample bay-area
