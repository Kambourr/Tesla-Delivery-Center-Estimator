"""The estimate and precompute path is ordinary Python. No model API."""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "dce"
_RUNTIME = ("orchestrator.py", "precompute", "model", "scenarios", "cli", "app", "geo")
_BANNED = ("openai", "anthropic", "litellm", "langchain", "dce.extract.pdf_llm")


def test_runtime_packages_do_not_import_an_llm() -> None:
    offenders: list[str] = []
    for name in _RUNTIME:
        root = SRC / name
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            for imported in _imports(path):
                if any(
                    imported == banned or imported.startswith(banned + ".") for banned in _BANNED
                ):
                    offenders.append(f"{path.relative_to(SRC)} imports {imported}")
    assert offenders == []


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found
