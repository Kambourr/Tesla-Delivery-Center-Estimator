"""Desktop entry for the delivery-center estimator.

The window is a system webview (pywebview) showing a local MapLibre page.
Calculate calls the orchestrator through :mod:`dce.app.results`. It must
not import ``dce.extract.pdf_llm``. Importing this module does not open a
window and does not import pywebview.
"""

from __future__ import annotations


def main() -> int:
    """Open the map. Returns 0 after the window closes."""
    from dce.app.desktop import launch

    return launch()
