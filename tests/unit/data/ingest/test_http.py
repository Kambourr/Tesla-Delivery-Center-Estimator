"""Allowlisted HTTP never leaves the public-data hosts and never follows redirects."""

from __future__ import annotations

import pytest

from dce.data.ingest.http import AllowlistError, host_allowed, redact_url, request_bytes


def test_host_allowlist_matches_documented_suffixes() -> None:
    assert host_allowed("api.census.gov")
    assert host_allowed("api.bls.gov")
    assert host_allowed("data.ca.gov")
    assert host_allowed("www.energy.ca.gov")
    assert not host_allowed("example.com")
    assert not host_allowed("evilcensus.gov")
    assert not host_allowed("census.gov.example.com")
    assert not host_allowed(None)
    assert not host_allowed("")


def test_request_refuses_off_allowlist_before_any_socket() -> None:
    with pytest.raises(AllowlistError, match="example.com"):
        request_bytes("https://example.com/acs")
    with pytest.raises(AllowlistError, match="http"):
        request_bytes("http://api.census.gov/data")
    with pytest.raises(AllowlistError, match="credentials"):
        request_bytes("https://user:secret@api.census.gov/data")


def test_redact_url_strips_key_query_parameters() -> None:
    url = "https://api.census.gov/data/2024/acs/acs5?get=NAME&key=secret-key&for=zcta"
    redacted = redact_url(url)
    assert "secret-key" not in redacted
    assert "key=[redacted]" in redacted
    assert "get=NAME" in redacted
