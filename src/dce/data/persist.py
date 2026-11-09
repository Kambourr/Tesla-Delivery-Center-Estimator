"""Write fetched public rows and their ``source_registry`` ``as_of``.

Ingest modules return dataclasses and do not open SQLite. This module is the
M2 composition step: it maps those dataclasses onto repository records and
records the dataset URL, ``as_of``, ``fetched_at``, and TTL. SQL stays in
:mod:`dce.storage.repository`.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from dce.data.ingest.bls_oews import OewsWage
from dce.data.ingest.ca_ev import EvZipCount
from dce.data.ingest.census_acs import ZctaAcs
from dce.storage.repository import (
    EvZipRecord,
    OewsWageRecord,
    SourceRecord,
    ZctaAcsRecord,
    upsert_ev_zip,
    upsert_oews_wage,
    upsert_source,
    upsert_zcta_acs,
)


class PersistError(Exception):
    """A public row could not be stored."""


def persist_zcta_acs(
    conn: sqlite3.Connection,
    rows: Sequence[ZctaAcs],
    *,
    source_id: str,
    url: str,
    as_of: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    """Upsert ACS rows and one registry row. ``url`` must not contain an API key."""
    if not rows:
        raise PersistError("Refusing to record a Census source with no ACS rows.")
    if "key=" in url.lower():
        raise PersistError("Census source URL must not include an API key.")
    for row in rows:
        upsert_zcta_acs(conn, _zcta_record(row), commit=False)
    _write_source(
        conn,
        source_id=source_id,
        url=url,
        as_of=as_of,
        fetched_at=fetched_at,
        ttl_days=ttl_days,
        license_note=license_note,
        byte_count=byte_count,
    )


def persist_oews_wage(
    conn: sqlite3.Connection,
    row: OewsWage,
    *,
    source_id: str,
    url: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    """Upsert one OEWS wage and the registry ``as_of`` from that row."""
    upsert_oews_wage(
        conn,
        OewsWageRecord(
            area_code=row.area_code,
            area_name=row.area_name,
            soc=row.soc,
            soc_title=row.soc_title,
            mean_annual=row.mean_annual,
            median_annual=row.median_annual,
            as_of=row.as_of,
        ),
        commit=False,
    )
    _write_source(
        conn,
        source_id=source_id,
        url=url,
        as_of=row.as_of,
        fetched_at=fetched_at,
        ttl_days=ttl_days,
        license_note=license_note,
        byte_count=byte_count,
    )


def persist_ev_zip(
    conn: sqlite3.Connection,
    rows: Sequence[EvZipCount],
    *,
    source_id: str,
    url: str,
    as_of: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    """Upsert ZIP vehicle rows and one registry row for that vintage."""
    if not rows:
        raise PersistError("Refusing to record a vehicle source with no ZIP rows.")
    for row in rows:
        if row.as_of != as_of:
            raise PersistError(f"ZIP {row.zip_code} as_of {row.as_of} does not match {as_of}.")
        upsert_ev_zip(conn, _ev_record(row), commit=False)
    _write_source(
        conn,
        source_id=source_id,
        url=url,
        as_of=as_of,
        fetched_at=fetched_at,
        ttl_days=ttl_days,
        license_note=license_note,
        byte_count=byte_count,
    )


def _write_source(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    url: str,
    as_of: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    upsert_source(
        conn,
        SourceRecord(
            source_id=source_id,
            url=url,
            as_of=as_of,
            fetched_at=fetched_at,
            ttl_days=ttl_days,
            license_note=license_note,
            byte_count=byte_count,
        ),
    )


def _zcta_record(row: ZctaAcs) -> ZctaAcsRecord:
    return ZctaAcsRecord(
        zcta=row.zcta,
        year=row.year,
        population=row.population,
        median_hh_income=row.median_hh_income,
        vehicles_available=row.vehicles_available,
        mean_commute=row.mean_commute,
        median_home_value=row.median_home_value,
    )


def _ev_record(row: EvZipCount) -> EvZipRecord:
    return EvZipRecord(
        zip_code=row.zip_code,
        state=row.state,
        bev=_whole(row.bev, what="bev"),
        phev=_whole(row.phev, what="phev"),
        fcev=_whole(row.fcev, what="fcev"),
        total_ldv=_whole(row.total_ldv, what="total_ldv"),
        as_of=row.as_of,
        source=row.source,
    )


def _whole(value: float | None, *, what: str) -> int | None:
    if value is None:
        return None
    if not value.is_integer() or value < 0:
        raise PersistError(f"{what} must be a whole number >= 0, got {value!r}.")
    return int(value)
