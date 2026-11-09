"""Optional LLM extraction for messy tariff PDFs.

Contract
--------
``extract_tariff_json(pdf_path, cache) -> dict``

This is the only module allowed to call an LLM API. It must:

- cache ``(pdf_sha256 -> json)`` in SQLite ``extract_cache`` with
  ``extractor='llm'`` before returning;
- refuse to run from ``dce.model`` or from the GUI calculate button
  (those layers must not import this module);
- leave the cost math deterministic: the model never sees a live LLM call.

If no key is configured, fail clearly and let the caller use
:mod:`dce.extract.pdf_manual` or EIA / OpenEI numbers. An LLM key is not
listed in ``.env.example`` in M0.

Milestone M0: stub. The function does not import an SDK and does not make
network calls.
"""

from __future__ import annotations

from pathlib import Path


def extract_tariff_json(pdf_path: Path, cache: Path) -> dict[str, object]:
    """Extract tariff fields with an LLM and cache the JSON. Not implemented in M0."""
    raise NotImplementedError("dce.extract.pdf_llm.extract_tariff_json is a stub (M0)")
