"""Delivery-Center Estimator (``dce``).

Public-data desktop app. Given a US ZIP code, a later milestone estimates
cost per delivery, the top three cost drivers, and a customer-base map.

Layers (see ``CONTRIBUTING.md``):

- ``data.ingest`` fetches allowlisted public sources.
- ``data`` resolves rent and staleness from stored rows.
- ``storage`` is the only SQLite boundary.
- ``model`` is pure calculation. No I/O, no network, no UI.
- ``scenarios`` replays the model. No I/O.
- ``geo`` builds the catchment map.
- ``app`` is the pywebview map. ``cli`` is the headless entry.
- ``extract.pdf_llm`` is the only module that may call an LLM.

Milestone M1 adds the SQLite schema, OS data paths, and local ZIP
resolution. Importing this package does no I/O and makes no network calls.

Hard rules:

- Public data only. Never Tesla internal data.
- Never scrape LoopNet, Crexi, or other ToS-prohibited listing sites.
- Core math is deterministic.
"""

__version__ = "0.0.0"
