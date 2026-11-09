"""Census TIGER / cartographic boundary loader.

Contract
--------
Allowlisted host: ``census.gov`` (TIGER/Line and TIGERweb). Store simplified
GeoJSON or GeoPackage for the queried county or state under the user data
directory, not the full national ZCTA extract inside git or the app bundle.
The San Mateo demo may later ship a small GeoPackage in ``data/demo/``.

No API key. No download in M0. Importing this module makes no network calls.
"""
