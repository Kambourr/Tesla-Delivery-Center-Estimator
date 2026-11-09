"""Delivery-Center Estimator (``dce``).

Public-data desktop app. Given a US ZIP code, a later milestone estimates
cost per delivery, the top three cost drivers, and a customer-base map.

Milestone M0 is a skeleton. Importing this package does no I/O and makes
no network calls. There is no product calculation here.

Hard rules for every later milestone:

- Public data only. Never Tesla internal data.
- Never scrape LoopNet, Crexi, or other ToS-prohibited listing sites.
- Core math is deterministic. An LLM client may exist only in
  ``dce.extract.pdf_llm`` and must never be imported by ``dce.model`` or by
  the calculate path.
"""

__version__ = "0.0.0"
