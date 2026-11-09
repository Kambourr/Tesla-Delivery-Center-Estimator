"""Refresh entry point for allowlisted public sources.

When implemented, this script will call ``dce.data.ingest`` fetchers and
hand the dataclasses to ``dce.storage.repository``. It must not scrape
LoopNet, Crexi, or broker PDFs. Milestone M0 does not fetch anything.
"""

from __future__ import annotations

raise SystemExit("scripts/refresh_public_data.py is an M0 stub. It does not fetch anything.")
