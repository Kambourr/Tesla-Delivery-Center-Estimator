"""Optional PDF extraction. Isolated from the cost model.

``pdf_manual`` is the default path (regex / tables for known PG&E schedules).
``pdf_llm`` may call an LLM API and must cache ``pdf_hash -> json``.
``dce.model`` and the GUI calculate path must not import ``pdf_llm``.

Milestone M0: stubs. No network calls.
"""
