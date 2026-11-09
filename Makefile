# Developer tasks. Prefer the project venv when it exists.
ifneq (,$(wildcard .venv/bin/python))
PYTHON := .venv/bin/python
else
PYTHON := python3
endif

.PHONY: setup lint typecheck test build check

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

# Packaging is a later milestone. The script exits 1 on purpose in M0.
build:
	./scripts/build_macos.sh

check: lint typecheck test
