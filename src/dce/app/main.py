"""Desktop entry for the delivery-center estimator.

The window is a system webview (pywebview) showing a local MapLibre page.
Calculate calls the orchestrator through :mod:`dce.app.results`. It must
not import ``dce.extract.pdf_llm``. Importing this module does not open a
window and does not import pywebview.
"""

from __future__ import annotations

import sys
import time


def main(argv: list[str] | None = None, *, started: float | None = None) -> int:
    """Open the map, or run ``--smoke`` without a window.

    ``--smoke`` reads the bundled results database and prints JSON. It does
    not import pywebview. The window path does, inside :func:`dce.app.desktop.launch`.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--smoke"]:
        from dce.app.smoke import run_smoke

        origin = time.perf_counter() if started is None else started
        return run_smoke(origin)
    from dce.app.desktop import launch

    return launch()
