"""Headless command-line package.

Contract: ``python -m dce --help`` prints usage and exits 0. The only
required input, once estimation exists, is a US ZIP. This package must not
import ``dce.extract.pdf_llm`` and must not open SQLite itself; it calls
:func:`dce.orchestrator.estimate`.
"""

from dce.cli.main import build_parser, main

__all__ = ["build_parser", "main"]
