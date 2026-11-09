"""Tkinter shell for the delivery-center estimator.

Contract
--------
- Required input: one US ZIP code.
- Scenario controls are preset buttons (mix, wage ±20%), not free-text rent.
- An optional advanced rent override may be added later. The default path
  must run with the ZIP alone.
- Show staleness badges and the rent tier / confidence / ``as_of``.
- "Open map" calls ``webbrowser.open`` on the Folium HTML path.
- Calculate calls :func:`dce.orchestrator.estimate`. It must not import
  ``dce.extract.pdf_llm``.
- Do not embed Qt WebEngine or any other browser widget.

Tkinter is the standard library. Do not add PySide6.

Milestone M0: ``main`` raises ``NotImplementedError`` and this module does
not import ``tkinter``, so importing it cannot open a window or require a
display.
"""

from __future__ import annotations


def main() -> int:
    """Launch the Tkinter window. Not implemented in M0."""
    raise NotImplementedError(
        "dce.gui.app.main is a stub (M0). The shell will be Tkinter; "
        "the map will open in the system browser."
    )
