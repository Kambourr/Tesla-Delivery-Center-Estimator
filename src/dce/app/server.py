"""Localhost server for the map page.

The desktop window and the headless smoke test both use it. It serves the
files under ``dce.app``'s ``web`` directory and the same three calls the
pywebview bridge exposes. It binds to 127.0.0.1 only.
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from dce.app.api import AppApi
from dce.app.paths import web_dir

_RESULT = re.compile(r"/api/result/(\d{5})$")
_COMPARE = re.compile(r"/api/compare/(\d{5})/(\d{5})$")
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".geojson": "application/geo+json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
}


class PreviewServer:
    """Serve the UI until :meth:`stop`."""

    def __init__(
        self,
        api: AppApi,
        host: str = "127.0.0.1",
        port: int = 0,
        pmtiles: Path | None = None,
    ) -> None:
        self._api = api
        self._host = host
        self._port = port
        self._pmtiles = pmtiles if pmtiles is not None and pmtiles.is_file() else None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        """Return the base URL. Raises if :meth:`start` has not run."""
        if self._httpd is None:
            raise RuntimeError("Preview server is not running.")
        host, port = self._httpd.server_address[:2]
        if isinstance(host, bytes):
            host = host.decode("ascii")
        return f"http://{host}:{port}/"

    def start(self) -> str:
        """Start the server on a background thread and return its base URL."""
        handler = _handler(self._api, web_dir(), self._pmtiles)
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="dce-preview",
            daemon=True,
        )
        self._thread.start()
        return self.url

    def stop(self) -> None:
        """Stop the server. Safe to call more than once."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def _handler(api: AppApi, web: Path, pmtiles: Path | None) -> type[BaseHTTPRequestHandler]:
    root = web.resolve()
    archive = pmtiles.resolve() if pmtiles is not None else None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = unquote(urlparse(self.path).path)
            if path == "/api/bootstrap":
                _send_json(self, api.bootstrap())
                return
            result_match = _RESULT.fullmatch(path)
            if result_match:
                _send_json(self, api.get_result(result_match.group(1)))
                return
            compare_match = _COMPARE.fullmatch(path)
            if compare_match:
                _send_json(self, api.compare(compare_match.group(1), compare_match.group(2)))
                return
            if path == "/tiles/zcta_us.pmtiles":
                if archive is None:
                    self.send_error(404)
                    return
                _send_range(self, archive, "application/octet-stream")
                return
            file_path = _static_file(root, path)
            if file_path is None:
                self.send_error(404)
                return
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", _TYPES.get(file_path.suffix, "application/octet-stream")
            )
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def _static_file(root: Path, url_path: str) -> Path | None:
    if url_path in {"", "/"}:
        url_path = "/index.html"
    relative = url_path.lstrip("/")
    if not relative or relative.startswith(("/", "\\")) or "\\" in relative:
        return None
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


_BYTE_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


def _send_range(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    """Serve one file, honoring a single ``Range: bytes=`` request.

    The PMTiles client reads the archive with range requests so a national
    tile set does not have to be downloaded up front.
    """
    size = path.stat().st_size
    start, end, partial = _range_bounds(handler.headers.get("Range"), size)
    if start is None or end is None:
        handler.send_response(416)
        handler.send_header("Content-Range", f"bytes */{size}")
        handler.end_headers()
        return
    length = end - start + 1
    handler.send_response(206 if partial else 200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if partial:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(remaining, 256 * 1024))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


def _range_bounds(header: str | None, size: int) -> tuple[int | None, int | None, bool]:
    """Return ``start``, ``end`` (inclusive), and whether the request was a range.

    ``(None, None, False)`` means the range was not satisfiable.
    """
    if size <= 0:
        if header:
            return None, None, False
        return 0, -1, False
    if not header:
        return 0, size - 1, False
    match = _BYTE_RANGE.fullmatch(header.strip())
    if match is None:
        return None, None, False
    raw_start, raw_end = match.group(1), match.group(2)
    if raw_start == "" and raw_end == "":
        return None, None, False
    if raw_start == "":
        suffix = int(raw_end)
        if suffix <= 0:
            return None, None, False
        start = max(size - suffix, 0)
        return start, size - 1, True
    start = int(raw_start)
    end = int(raw_end) if raw_end else size - 1
    if start >= size or start > end:
        return None, None, False
    return start, min(end, size - 1), True


def _send_json(handler: BaseHTTPRequestHandler, payload: object) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)
