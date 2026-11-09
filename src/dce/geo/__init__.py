"""Catchment geometry, ZIP resolution, and Folium HTML.

Contract: build polygons and write ``outputs/maps/{zip}_{timestamp}.html``.
The Tkinter shell opens that file in the system browser. This package does
not embed a web view and does not calculate cost. Network tile downloads
are out of scope; prefer geometry with no external tile URLs.

``resolve_zip`` reads the bundled seed ``data/seed/zip_crosswalk.csv``.
The HUD download itself lives in ``dce.data.ingest.hud_crosswalk``.
"""
