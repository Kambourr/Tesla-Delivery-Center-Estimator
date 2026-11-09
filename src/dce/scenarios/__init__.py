"""Scenario grid and rank-stability checks.

Contract: call ``dce.model`` on inputs the orchestrator already loaded.
No file I/O, no SQLite, no network, no GUI, and no LLM. Wage shocks must
not be implemented here by re-reading rent from disk; the model applies
``Scenario.wage_shock`` to labor only.
"""
