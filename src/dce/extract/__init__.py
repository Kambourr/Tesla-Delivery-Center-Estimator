"""Optional PDF extraction, isolated from the cost model.

``pdf_manual`` is the default path. ``pdf_llm`` is the only module that may
call an LLM, and only to fill ``extract_cache``. ``dce.model``,
``dce.scenarios``, and the calculate path must not import ``pdf_llm``.
"""
