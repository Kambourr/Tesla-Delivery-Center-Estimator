"""Hand-coded parsers for known utility tariff PDFs.

Contract
--------
Extract structured energy and demand charges from published schedules
(demo: PG&E B-10 and B-19) into JSON cached in ``extract_cache`` with
``extractor='manual'``. Do not commit the PDF bytes or verbatim copyrighted
tariff text to git. Record ``as_of`` from the advice header.

This is the default offline path. No LLM. No network at import time.

Milestone M0: stub.
"""

from __future__ import annotations

from pathlib import Path


def extract_tariff_json(pdf_path: Path, cache: Path) -> dict:
    """Parse a known tariff PDF into JSON. Not implemented in M0."""
    raise NotImplementedError("dce.extract.pdf_manual.extract_tariff_json is a stub (M0)")
