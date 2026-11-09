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

Milestone M0: stub. ``data/seed/`` is empty. No network calls.
"""
