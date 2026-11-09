"""Deterministic cost and demand math.

Pure functions: frozen dataclasses in, numbers or dataclasses out. No file
I/O, no SQLite, no network, no GUI, and no import of ``dce.extract``,
``dce.storage``, ``dce.data``, ``dce.geo``, ``dce.app``, ``dce.cli``, or
``dce.scenarios``.

Modules
-------
``types``        shared frozen dataclasses (the MODULE_CONTRACTS types)
``assumptions``  strict typed view of ``data/defaults/assumptions.yaml``
``demand``       annual delivery proxy
``costs``        annualized components, ``$/delivery``, ``CostInputs`` builder
``drivers``      top-N cost drivers with shares
``errors``       typed errors; every one is a ``ValueError``

Scenario expansion lives in ``dce.scenarios`` so this package stays a
single calculation pass.
"""
