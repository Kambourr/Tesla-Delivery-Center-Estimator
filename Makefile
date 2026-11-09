# Developer tasks. Prefer the project venv when it exists.
ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python3
endif

.PHONY: setup lint typecheck test build check app zip-inputs zcta-boundaries

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
build:
	./scripts/build_macos.sh

# Open the pywebview map. Needs a display.
app:
	$(PYTHON) -m dce.app

check: lint typecheck test

# Public-data extracts. Not part of CI. See docs/DATA_SOURCES.md.
zip-inputs:
	$(PYTHON) scripts/build_zip_inputs.py --cache /tmp/dce-public --fetch-bls --fetch-zev

zcta-boundaries:
	$(PYTHON) scripts/build_zcta_boundaries.py --cache /tmp/dce-public
