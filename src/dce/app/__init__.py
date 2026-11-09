"""Tkinter desktop shell.

Contract: the only required field is a US ZIP. The Folium map opens in the
system browser via ``webbrowser.open``. Calculate calls
:func:`dce.orchestrator.estimate` and must not import ``dce.extract.pdf_llm``.
Do not add PySide6 or an embedded web engine.

Milestone M0 does not import Tkinter, so importing this package does not
need a display.
"""

from dce.app.main import main

__all__ = ["main"]
