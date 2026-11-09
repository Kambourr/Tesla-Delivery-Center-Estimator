"""Allowlisted HTTP for public-data ingest.

Fetch policy is ``docs/DATA_SOURCES.md``: census.gov, bls.gov, huduser.gov,
eia.gov, openei.org, energy.ca.gov, data.ca.gov, and pge.com. Nothing else
is contacted. Redirects are refused so a missing Census key (HTTP 302) cannot
be stored as a successful response and a redirect cannot leave the allowlist.

This module does not open SQLite and does not read API keys. Callers redact
secrets before they log a URL; :func:`redact_url` strips common key parameters.
"""

from __future__ import annotations

import json
from http.client import HTTPMessage
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_ALLOWED_HOST_SUFFIXES: tuple[str, ...] = (
    "census.gov",
    "bls.gov",
    "huduser.gov",
    "eia.gov",
    "openei.org",
    "energy.ca.gov",
    "data.ca.gov",
    "pge.com",
)
_SECRET_QUERY_NAMES = frozenset({"key", "registrationkey", "token", "api_key", "apikey"})
_USER_AGENT = "delivery-center-estimator"
_MAX_BYTES = 5_000_000


class IngestError(Exception):
    """An allowlisted public fetch failed."""


class AllowlistError(IngestError):
    """The URL is not an https URL on the public-data host allowlist."""


def host_allowed(hostname: str | None) -> bool:
    """Return whether ``hostname`` is an allowlisted public-data host."""
    if hostname is None:
        return False
    host = hostname.lower().rstrip(".")
    if host == "" or ":" in host:
        return False
    for suffix in _ALLOWED_HOST_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def redact_url(url: str) -> str:
    """Return ``url`` with query secrets replaced by ``[redacted]``."""
    parts = urlsplit(url)
    kept: list[str] = []
    for piece in parts.query.split("&"):
        if piece == "":
            continue
        name, separator, _value = piece.partition("=")
        if name.lower() in _SECRET_QUERY_NAMES and separator == "=":
            kept.append(f"{name}=[redacted]")
        else:
            kept.append(piece)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


def request_bytes(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    max_bytes: int = _MAX_BYTES,
) -> bytes:
    """Fetch one allowlisted URL. Raises :class:`IngestError` on failure.

    The default cap is 5 MiB, which covers OEWS and ACS JSON. The California
    fuel-type loader uses the datastore SQL API so it does not download the
    multi-megabyte CSV. Callers that need a larger public file (the CEC ZEV
    workbook is about 6 MiB) pass ``max_bytes``.
    """
    cap = _require_max_bytes(max_bytes)
    _require_allowed(url)
    request_headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json, text/csv, */*",
    }
    if headers:
        request_headers.update(headers)
    request = Request(url, data=body, headers=request_headers, method=method)
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(cap + 1)
    except HTTPError as exc:
        exc.read(cap)
        raise IngestError(
            f"{urlparse(url).hostname} returned HTTP {exc.code} for {redact_url(url)}."
        ) from exc
    except URLError as exc:
        raise IngestError(f"Could not reach {urlparse(url).hostname}.") from exc
    if len(payload) > cap:
        raise IngestError(f"{urlparse(url).hostname} response exceeded {cap} bytes.")
    return bytes(payload)


def request_json(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    max_bytes: int = _MAX_BYTES,
) -> object:
    """Fetch one allowlisted URL and parse the body as JSON."""
    raw = request_bytes(
        url,
        method=method,
        body=body,
        headers=headers,
        timeout=timeout,
        max_bytes=max_bytes,
    )
    try:
        parsed: object = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestError(f"{urlparse(url).hostname} did not return JSON.") from exc
    return parsed


def encode_query(params: dict[str, str]) -> str:
    """Encode a query string, keeping colons so Census ``for=`` matches the docs."""
    parts = [f"{quote(key, safe='')}={quote(value, safe=':')}" for key, value in params.items()]
    return "&".join(parts)


def _require_max_bytes(max_bytes: int) -> int:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise IngestError(f"max_bytes must be a positive integer, got {max_bytes!r}.")
    return max_bytes


def _require_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not host_allowed(parsed.hostname):
        raise AllowlistError(
            "Refusing to fetch a URL that is not https on the public-data allowlist: "
            f"{parsed.scheme}://{parsed.hostname}."
        )
    if parsed.username is not None or parsed.password is not None:
        raise AllowlistError("Refusing a URL that embeds credentials.")


class _RejectRedirects(HTTPRedirectHandler):
    """Fail closed. Allowlisted calls in this milestone answer with HTTP 200."""

    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> Request | None:
        del req, fp, msg, headers
        raise IngestError(
            f"Refusing HTTP {code} redirect to {urlparse(newurl).hostname}. "
            "Public loaders do not follow redirects."
        )
