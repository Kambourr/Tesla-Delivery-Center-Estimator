"""Staleness is computed from as_of and ttl_days. It is not a stored column."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from dce.data.registry import TTL_18_MONTHS_DAYS, parse_as_of, staleness_status


def test_missing_when_as_of_is_absent() -> None:
    today = date(2026, 11, 9)
    assert staleness_status(None, TTL_18_MONTHS_DAYS, today) == "missing"
    assert parse_as_of(None) is None
    assert parse_as_of("   ") is None
    assert staleness_status(parse_as_of(""), 10, today) == "missing"


def test_fresh_aging_and_stale_split_the_ttl_in_half() -> None:
    today = date(2026, 11, 9)
    ttl = 10
    assert staleness_status(today, ttl, today) == "fresh"
    assert staleness_status(today - timedelta(days=5), ttl, today) == "fresh"
    assert staleness_status(today - timedelta(days=6), ttl, today) == "aging"
    assert staleness_status(today - timedelta(days=10), ttl, today) == "aging"
    assert staleness_status(today - timedelta(days=11), ttl, today) == "stale"


def test_future_as_of_is_fresh_and_zero_ttl_has_no_aging_window() -> None:
    today = date(2026, 11, 9)
    assert staleness_status(today + timedelta(days=3), 548, today) == "fresh"
    assert staleness_status(today, 0, today) == "fresh"
    assert staleness_status(today - timedelta(days=1), 0, today) == "stale"


def test_eighteen_month_horizon_matches_the_data_sources_rule() -> None:
    today = date(2026, 11, 9)
    # 548 days is 18 months. Half of that is still fresh; one day past is stale.
    assert staleness_status(today - timedelta(days=274), TTL_18_MONTHS_DAYS, today) == "fresh"
    assert staleness_status(today - timedelta(days=275), TTL_18_MONTHS_DAYS, today) == "aging"
    assert staleness_status(today - timedelta(days=548), TTL_18_MONTHS_DAYS, today) == "aging"
    assert staleness_status(today - timedelta(days=549), TTL_18_MONTHS_DAYS, today) == "stale"


def test_datetime_uses_the_calendar_date() -> None:
    today = datetime(2026, 11, 9, 23, 59, 59)
    as_of = datetime(2026, 11, 9, 0, 0, 0)
    assert staleness_status(as_of, 0, today) == "fresh"


def test_negative_ttl_and_bad_dates_raise() -> None:
    today = date(2026, 11, 9)
    with pytest.raises(ValueError, match="ttl_days"):
        staleness_status(today, -1, today)
    with pytest.raises(ValueError, match="ISO date"):
        parse_as_of("May 2025")
    assert parse_as_of("2025-05-01T00:00:00Z") == date(2025, 5, 1)
