"""Deterministic cost and demand math.

Pure functions: frozen dataclasses in, numbers or dataclasses out. No file
I/O, no SQLite, no network, no GUI, and no import of ``dce.extract``,
``dce.storage``, ``dce.data``, ``dce.geo``, ``dce.app``, ``dce.cli``, or
``dce.scenarios``.

Scenario expansion lives in ``dce.scenarios`` so this package stays a
single calculation pass.
"""
