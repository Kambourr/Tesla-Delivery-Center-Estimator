"""Desktop shell: a pywebview window and a local MapLibre page.

The only required input is a US ZIP. The page calls
:class:`dce.app.api.AppApi` for the map, one ZIP's dashboard, and a
two-ZIP comparison. That path calls :func:`dce.orchestrator.estimate`'s
pipeline and must not import ``dce.extract.pdf_llm``.

Importing this package does not open a window, import pywebview, or
require a display.
"""

from dce.app.main import main

__all__ = ["main"]
