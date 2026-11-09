"""Curated industrial asking-rent seed (no scrapers).

Contract
--------
Load the bundled CBSA industrial asking-rent table into ``rent_cbsa``.
Each row has ``cbsa``, ``property_type`` (industrial / flex / retail /
auto_service), ``rent_psf_year``, ``as_of``, ``citation``, and ``broker``
(CBRE, Cushman, Colliers, or JLL public market reports).

Figures are manually curated headline rents with citations. This module
must not download, scrape, or parse LoopNet, Crexi, CoStar, or broker PDFs
at runtime. A later curator script may help a human update the seed; it is
not on the estimate path.

Refresh cadence for the seed is quarterly. Aging after 2 quarters, stale
after 4.

``read_rent_seed`` parses the curated file and returns rows. It does not
open SQLite and it does not download anything. The repository upserts the
rows. See ``data/seed/README.md`` for provenance.

Milestone M0: stub. ``data/seed/`` has no rent rows yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CbsaRentSeed:
    """One metro industrial asking-rent headline from a cited public report."""

    cbsa: str
    property_type: str
    rent_psf_year: float
    as_of: str
    citation: str
    broker: str


def read_rent_seed(path: Path) -> tuple[CbsaRentSeed, ...]:
    """Read the bundled rent seed file. Not implemented in M0."""
    raise NotImplementedError("dce.data.rent_defaults.read_rent_seed is a stub (M0)")
