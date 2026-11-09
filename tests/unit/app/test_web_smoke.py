"""Headless smoke test. No display, no network, no pywebview window."""

from __future__ import annotations

import http.client
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from dce.app.api import AppApi
from dce.app.results import UI_RESULT_SCHEMA
from dce.app.server import PreviewServer

WEB = Path(__file__).resolve().parents[3] / "src" / "dce" / "app" / "web"
REMOTE_HINTS = (
    "unpkg.com",
    "jsdelivr.net",
    "cdnjs.cloudflare.com",
    "googleapis.com",
    "cdn.jsdelivr.net",
)


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []
        self.icons: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs if value is not None}
        if tag == "script" and "src" in values:
            self.scripts.append(values["src"])
        if tag == "link" and values.get("rel") == "stylesheet" and "href" in values:
            self.stylesheets.append(values["href"])
        if tag == "link" and values.get("rel") == "icon" and "href" in values:
            self.icons.append(values["href"])


def _result(zip_code: str) -> dict[str, object]:
    return {"schema": UI_RESULT_SCHEMA, "zip_code": zip_code, "cost_per_delivery": 500.0}


def test_page_assets_are_local_and_the_bridge_methods_exist() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    style = json.loads((WEB / "vendor" / "basemap-style.json").read_text(encoding="utf-8"))
    library = (WEB / "vendor" / "maplibre-gl.js").read_text(encoding="utf-8")
    tags = _Tags()
    tags.feed(page)
    assert tags.scripts == ["vendor/maplibre-gl.js", "app.js"]
    assert tags.stylesheets == ["vendor/maplibre-gl.css", "app.css"]
    assert len(tags.icons) == 1 and tags.icons[0].startswith("data:image/svg+xml")
    for url in tags.scripts + tags.stylesheets + tags.icons:
        assert not url.startswith(("http://", "https://", "//"))
    blob = page + script
    for host in REMOTE_HINTS:
        assert host not in blob
    assert "bootstrap" in script and "get_result" in script and "compare" in script
    for name in ("bootstrap", "get_result", "compare"):
        assert hasattr(AppApi, name)
    assert library.startswith("/**")
    assert "MapLibre GL JS" in library.splitlines()[1]
    assert len(library) > 100_000
    assert "openmaptiles" in style["sources"]
    glyphs = style["glyphs"]
    assert isinstance(glyphs, str) and glyphs.startswith("https://")


def test_preview_server_serves_the_page_and_the_api(tmp_path: Path) -> None:
    folder = tmp_path / "ui_results"
    folder.mkdir()
    (folder / "94402.json").write_text(json.dumps(_result("94402")), encoding="utf-8")
    (folder / "94404.json").write_text(json.dumps(_result("94404")), encoding="utf-8")
    api = AppApi(results_path=folder)
    server = PreviewServer(api)
    try:
        base = server.start()
        page = urlopen(base, timeout=5)
        html = page.read().decode("utf-8")
        assert page.status == 200
        assert 'id="map"' in html
        assert 'id="panel"' in html
        library = urlopen(base + "vendor/maplibre-gl.js", timeout=5)
        assert library.status == 200
        assert len(library.read()) > 100_000
        bootstrap = json.loads(urlopen(base + "api/bootstrap", timeout=5).read().decode("utf-8"))
        assert bootstrap["ok"] is True
        assert any(
            feature["properties"]["zip"] == "94402" for feature in bootstrap["zcta"]["features"]
        )
        result = json.loads(urlopen(base + "api/result/94402", timeout=5).read().decode("utf-8"))
        assert result["ok"] is True
        assert result["source"] == "precomputed"
        compared = json.loads(
            urlopen(base + "api/compare/94402/94404", timeout=5).read().decode("utf-8")
        )
        assert compared["ok"] is True
        assert compared["schema"] == "dce.ui_compare.v1"
        try:
            urlopen(base + "api/result/12ab", timeout=5)
            raise AssertionError("expected a 404")
        except HTTPError as exc:
            assert exc.code == 404
        parsed = urlparse(base)
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=5)
        connection.request("GET", "/../../pyproject.toml")
        escaped = connection.getresponse()
        assert escaped.status == 404
        escaped.read()
    finally:
        server.stop()
        api.close()
