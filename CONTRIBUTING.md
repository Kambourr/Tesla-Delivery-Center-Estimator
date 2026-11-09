# Contributing

Student project. Keep changes small, typed, and inside the layer that owns them.
Public data only. Never Tesla internal files. Never scrape LoopNet, Crexi, or
other listing sites. An LLM call is allowed only in `dce.extract.pdf_llm`.

Decisions that are already made live in `docs/adr/`. Do not reopen them in a
pull request unless Jacob asks.

## Setup

```bash
make setup
source .venv/bin/activate
pre-commit install   # already run by make setup
make check           # lint, typecheck, tests
python -m dce --help
```

`make build` is the macOS packaging entry. In M0 it exits 1. It does not run
PyInstaller yet.

Tool versions and options live in `pyproject.toml` only (ruff, mypy, pytest,
coverage). Pre-commit runs ruff. CI runs ruff, mypy, and pytest. mypy is not
in pre-commit because it needs this environment and the geo stack.

## Layout

| Path | Owns | Must not |
|---|---|---|
| `dce.data.ingest` | `fetch_*` from allowlisted hosts. Returns frozen dataclasses. | Open SQLite, compute cost, import `dce.model` math |
| `dce.data` | Staleness, rent seed parsing, `resolve_rent` | Scrape listings, call an LLM |
| `dce.storage` | Connections, migrations, SQL | HTTP, cost math, Tkinter |
| `dce.model` | One-pass deterministic math | I/O, network, UI, `dce.scenarios`, `dce.extract` |
| `dce.scenarios` | Mix and shock grid, rank correlation | I/O. Call `dce.model` on values already loaded |
| `dce.geo` | ZIP resolution from local data, catchment, Folium HTML | Embedded browser, cost math, live tile downloads |
| `dce.app` | Tkinter. Opens the map with `webbrowser.open` | `dce.extract.pdf_llm`, PySide6 |
| `dce.cli` | Argparse. ZIP is the only required input | SQLite of its own, `pdf_llm` |
| `dce.orchestrator` | Wires the layers for one ZIP | Live LLM calls |
| `dce.extract` | PDF to JSON. `pdf_llm` is isolated | Being imported by `model` or the calculate path |

`dce.orchestrator.estimate` is the composition root. The CLI and the Tkinter
shell call it. They do not reach into SQLite themselves.

Shared result types are frozen dataclasses in `dce.model.types`. Layer-specific
records (a fetched ACS row, a registry row, a rent resolution) live next to
the function that returns them. Do not add pydantic for this.

## Naming

- Modules and packages: `snake_case`. Package import is `dce`.
- Functions and variables: `snake_case`. Classes: `PascalCase`.
- Constants: `UPPER_SNAKE`.
- ZIP codes, FIPS, CBSA, and SOC codes are `str`, so leading zeros survive.
- Ingest: `fetch_*` hits the network and returns a dataclass.
- Repository: `get_*` / `load_*` read SQLite; `upsert_*` writes it.
- Seed files: `read_*` parses a local file and returns dataclasses.
- Model functions take dataclasses and return dataclasses or plain numbers.
- Tests: `tests/unit/<layer>/test_<module>.py` maps to `src/dce/<layer>/<module>.py`.
  Integration tests that need a network stay in `tests/integration/` and must
  be optional so CI can run with no secrets.
- Fixtures: `tests/fixtures/`.

Private helpers start with `_`. Do not abbreviate except names that are already
the public term (`acs`, `cbsa`, `oews`, `qcew`, `zip`, `pdf`, `hud`).

## Tests and coverage

`make test` runs pytest with a coverage report. There is no coverage gate yet.
Add one when the model has real branches worth protecting. A boundary test in
`tests/unit/test_layer_boundaries.py` fails if `model` or `scenarios` grow I/O
imports, or if `pdf_llm` is imported outside `extract`.

## License

`LICENSE` is a placeholder. The project has no chosen license. See
`docs/OPEN_QUESTIONS.md`. Do not paste in MIT or Apache text until Jacob picks one.

## Data

Bundled seed goes in `data/seed/`. Read `data/seed/README.md` before adding a
file. Cite broker headlines. Do not commit tariff PDFs, teardown tables, API
keys, or Tesla extracts.
