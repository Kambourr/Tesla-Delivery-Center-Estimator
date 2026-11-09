"""Open the map in a pywebview window.

pywebview is imported here, not at package import, so headless CI can
import ``dce.app`` without a display and without the native webview
libraries. On macOS the window is WKWebView. The page itself is the local
HTML under ``dce.app.web``.
"""

from __future__ import annotations

from dce.app.api import AppApi
from dce.app.paths import (
    basemap_style,
    ui_cache_dir,
    ui_results_path,
    zcta_geojson_path,
    zcta_pmtiles_path,
)
from dce.app.server import PreviewServer


def launch() -> int:
    """Show the desktop window. Blocks until the window closes."""
    api = AppApi(
        zcta_path=zcta_geojson_path(),
        results_path=ui_results_path(),
        cache_dir=ui_cache_dir(),
        persist_cache=True,
        basemap_style=basemap_style(),
        use_repository=True,
        pmtiles_path=zcta_pmtiles_path(),
    )
    server = PreviewServer(api, pmtiles=zcta_pmtiles_path())
    url = server.start()
    try:
        import webview

        webview.create_window(
            "Delivery Center Estimator",
            url=url,
            js_api=api,
            width=1440,
            height=920,
            min_size=(960, 640),
            background_color="#121417",
            text_select=True,
        )
        webview.start()
    finally:
        server.stop()
        api.close()
    return 0
