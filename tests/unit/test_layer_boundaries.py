"""Layer import rules. Parses source files only; no network and no SQLite."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "dce"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _hits(module: str, banned: tuple[str, ...]) -> str | None:
    for item in banned:
        if module == item or module.startswith(item + "."):
            return item
    return None


def _python_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def test_model_does_not_import_io_or_other_layers() -> None:
    banned = (
        "dce.data",
        "dce.storage",
        "dce.scenarios",
        "dce.geo",
        "dce.app",
        "dce.cli",
        "dce.extract",
        "dce.orchestrator",
        "sqlite3",
        "requests",
        "urllib",
        "httpx",
        "tkinter",
        "webbrowser",
        "folium",
        "geopandas",
        "pathlib",
    )
    for path in _python_files(SRC / "model"):
        for module in _imported_modules(path):
            hit = _hits(module, banned)
            assert hit is None, f"{path.relative_to(SRC)} imports {module}"


def test_scenarios_do_not_import_io() -> None:
    banned = (
        "dce.data",
        "dce.storage",
        "dce.geo",
        "dce.app",
        "dce.cli",
        "dce.extract",
        "sqlite3",
        "requests",
        "urllib",
        "httpx",
        "tkinter",
        "webbrowser",
        "folium",
        "pathlib",
    )
    for path in _python_files(SRC / "scenarios"):
        for module in _imported_modules(path):
            hit = _hits(module, banned)
            assert hit is None, f"{path.relative_to(SRC)} imports {module}"


def test_zip_resolve_does_not_use_sql_or_network() -> None:
    banned = ("sqlite3", "requests", "urllib", "httpx", "http.client")
    for module in _imported_modules(SRC / "geo" / "resolve.py"):
        hit = _hits(module, banned)
        assert hit is None, f"geo/resolve.py imports {module}"


def test_m2_loaders_do_not_open_sqlite_or_import_storage() -> None:
    banned = ("sqlite3", "dce.storage", "dce.model", "dce.extract")
    loaders = ("census_acs.py", "bls_oews.py", "ca_ev.py")
    ingest = SRC / "data" / "ingest"
    for name in loaders:
        for module in _imported_modules(ingest / name):
            hit = _hits(module, banned)
            assert hit is None, f"data/ingest/{name} imports {module}"


def test_pdf_llm_stays_inside_extract() -> None:
    for path in _python_files(SRC):
        if path.name == "pdf_llm.py":
            continue
        for module in _imported_modules(path):
            assert module != "dce.extract.pdf_llm", f"{path.relative_to(SRC)} imports pdf_llm"
