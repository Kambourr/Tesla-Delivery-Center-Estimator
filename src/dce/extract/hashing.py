"""Content hashes for extract-cache keys.

Contract
--------
``sha256_file(path) -> str`` returns the hex SHA-256 of a file. The PDF
extractor uses it as ``extract_cache.pdf_sha256``. Pure local I/O when
implemented. No network.

Milestone M0: raises ``NotImplementedError`` and does not open the path.
"""

from __future__ import annotations

from pathlib import Path


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of ``path``. Not implemented in M0."""
    raise NotImplementedError("dce.extract.hashing.sha256_file is a stub (M0)")
