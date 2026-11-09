"""Public-data loaders and the rent resolver.

Contract: ``fetch_*`` functions (later) are the only network boundary, and
only to allowlisted hosts. ``load_*`` / ``upsert_*`` read and write SQLite.
The rent resolver reads the bundled seed and never scrapes listings.

Milestone M0 implements none of this. Importing the package makes no
network calls.
"""
