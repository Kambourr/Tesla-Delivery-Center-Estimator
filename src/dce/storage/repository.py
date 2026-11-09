"""Typed read and write functions for SQLite.

Contract
--------
All SQL lives here (and in ``migrate``). Ingest modules return dataclasses;
the orchestrator passes those dataclasses to ``upsert_*``. ``load_*`` and
``get_*`` return dataclasses or ``None``. No business rules, no HTTP, no
cost math.

M1 implements the ``source_registry`` pair. M2 adds ``zcta_acs``,
``oews_wage``, and ``ev_zip``. The ZIP crosswalk tables are created by
``migrate`` and still have no writers here.

``upsert_*`` commits by default so the row is durable. Pass ``commit=False``
when a caller writes several rows and a registry ``as_of`` in one transaction;
the last ``upsert_source`` commits them together.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceRecord:
    """One ``source_registry`` row.

    ``as_of`` and ``fetched_at`` are ISO-8601 text. ``byte_count`` maps to
    the ``bytes`` column. Staleness is computed later from ``as_of`` and
    ``ttl_days``; it is not a column.
    """

    source_id: str
    url: str
    as_of: str | None
    fetched_at: str | None
    ttl_days: int
    license_note: str
    byte_count: int | None


def get_source(conn: sqlite3.Connection, source_id: str) -> SourceRecord | None:
    """Return one registry row, or ``None`` when it was never stored."""
    query = (
        "SELECT source_id, url, as_of, fetched_at, ttl_days, license_note, bytes "
        "FROM source_registry WHERE source_id = ?"
    )
    row = conn.execute(query, (source_id,)).fetchone()
    if row is None:
        return None
    return _source_from_row(row)


def upsert_source(conn: sqlite3.Connection, record: SourceRecord, *, commit: bool = True) -> None:
    """Insert or replace one registry row. Commits unless ``commit`` is false."""
    conn.execute(
        """
        INSERT INTO source_registry (
            source_id, url, as_of, fetched_at, ttl_days, license_note, bytes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            url = excluded.url,
            as_of = excluded.as_of,
            fetched_at = excluded.fetched_at,
            ttl_days = excluded.ttl_days,
            license_note = excluded.license_note,
            bytes = excluded.bytes
        """,
        (
            record.source_id,
            record.url,
            record.as_of,
            record.fetched_at,
            record.ttl_days,
            record.license_note,
            record.byte_count,
        ),
    )
    if commit:
        conn.commit()


def list_sources(conn: sqlite3.Connection) -> list[SourceRecord]:
    """Return every registry row, ordered by ``source_id``."""
    query = (
        "SELECT source_id, url, as_of, fetched_at, ttl_days, license_note, bytes "
        "FROM source_registry ORDER BY source_id"
    )
    return [_source_from_row(row) for row in conn.execute(query)]


@dataclass(frozen=True)
class ZctaAcsRecord:
    """One ``zcta_acs`` row, including the version-2 median home value."""

    zcta: str
    year: int
    population: float | None
    median_hh_income: float | None
    vehicles_available: float | None
    mean_commute: float | None
    median_home_value: float | None


@dataclass(frozen=True)
class OewsWageRecord:
    """One ``oews_wage`` row. ``as_of`` is ISO text. Wages are annual dollars."""

    area_code: str
    area_name: str
    soc: str
    soc_title: str
    mean_annual: float | None
    median_annual: float | None
    as_of: str


@dataclass(frozen=True)
class EvZipRecord:
    """One ``ev_zip`` row. Counts are whole vehicles. ``source`` is cec, dmv, or fallback."""

    zip_code: str
    state: str
    bev: int | None
    phev: int | None
    fcev: int | None
    total_ldv: int | None
    as_of: str
    source: str


def get_zcta_acs(conn: sqlite3.Connection, zcta: str, year: int) -> ZctaAcsRecord | None:
    """Return one ACS row, or ``None`` when that ZCTA and year were never stored."""
    query = (
        "SELECT zcta, year, population, median_hh_income, vehicles_available, "
        "mean_commute, median_home_value FROM zcta_acs WHERE zcta = ? AND year = ?"
    )
    row = conn.execute(query, (zcta, year)).fetchone()
    if row is None:
        return None
    return _zcta_from_row(row)


def upsert_zcta_acs(
    conn: sqlite3.Connection, record: ZctaAcsRecord, *, commit: bool = True
) -> None:
    """Insert or replace one ACS row."""
    conn.execute(
        """
        INSERT INTO zcta_acs (
            zcta, year, population, median_hh_income, vehicles_available,
            mean_commute, median_home_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zcta, year) DO UPDATE SET
            population = excluded.population,
            median_hh_income = excluded.median_hh_income,
            vehicles_available = excluded.vehicles_available,
            mean_commute = excluded.mean_commute,
            median_home_value = excluded.median_home_value
        """,
        (
            record.zcta,
            record.year,
            record.population,
            record.median_hh_income,
            record.vehicles_available,
            record.mean_commute,
            record.median_home_value,
        ),
    )
    if commit:
        conn.commit()


def get_oews_wage(
    conn: sqlite3.Connection, area_code: str, soc: str, as_of: str
) -> OewsWageRecord | None:
    """Return one metro wage row, or ``None`` when it was never stored."""
    query = (
        "SELECT area_code, area_name, soc, soc_title, mean_annual, median_annual, as_of "
        "FROM oews_wage WHERE area_code = ? AND soc = ? AND as_of = ?"
    )
    row = conn.execute(query, (area_code, soc, as_of)).fetchone()
    if row is None:
        return None
    return _oews_from_row(row)


def upsert_oews_wage(
    conn: sqlite3.Connection, record: OewsWageRecord, *, commit: bool = True
) -> None:
    """Insert or replace one OEWS wage row."""
    conn.execute(
        """
        INSERT INTO oews_wage (
            area_code, area_name, soc, soc_title, mean_annual, median_annual, as_of
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(area_code, soc, as_of) DO UPDATE SET
            area_name = excluded.area_name,
            soc_title = excluded.soc_title,
            mean_annual = excluded.mean_annual,
            median_annual = excluded.median_annual
        """,
        (
            record.area_code,
            record.area_name,
            record.soc,
            record.soc_title,
            record.mean_annual,
            record.median_annual,
            record.as_of,
        ),
    )
    if commit:
        conn.commit()


def get_ev_zip(
    conn: sqlite3.Connection, zip_code: str, as_of: str, source: str
) -> EvZipRecord | None:
    """Return one ZIP vehicle row, or ``None`` when it was never stored."""
    query = (
        "SELECT zip, state, bev, phev, fcev, total_ldv, as_of, source "
        "FROM ev_zip WHERE zip = ? AND as_of = ? AND source = ?"
    )
    row = conn.execute(query, (zip_code, as_of, source)).fetchone()
    if row is None:
        return None
    return _ev_from_row(row)


def upsert_ev_zip(conn: sqlite3.Connection, record: EvZipRecord, *, commit: bool = True) -> None:
    """Insert or replace one ZIP vehicle row."""
    conn.execute(
        """
        INSERT INTO ev_zip (
            zip, state, bev, phev, fcev, total_ldv, as_of, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zip, as_of, source) DO UPDATE SET
            state = excluded.state,
            bev = excluded.bev,
            phev = excluded.phev,
            fcev = excluded.fcev,
            total_ldv = excluded.total_ldv
        """,
        (
            record.zip_code,
            record.state,
            record.bev,
            record.phev,
            record.fcev,
            record.total_ldv,
            record.as_of,
            record.source,
        ),
    )
    if commit:
        conn.commit()


def _source_from_row(row: sqlite3.Row | tuple[object, ...]) -> SourceRecord:
    source_id, url, as_of, fetched_at, ttl_days, license_note, byte_count = row
    return SourceRecord(
        source_id=str(source_id),
        url=str(url),
        as_of=None if as_of is None else str(as_of),
        fetched_at=None if fetched_at is None else str(fetched_at),
        ttl_days=_required_int(ttl_days),
        license_note=str(license_note),
        byte_count=_optional_int(byte_count),
    )


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected an integer from SQLite, got {value!r}.")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _zcta_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZctaAcsRecord:
    zcta, year, population, income, vehicles, commute, home_value = row
    return ZctaAcsRecord(
        zcta=str(zcta),
        year=_required_int(year),
        population=_optional_float(population),
        median_hh_income=_optional_float(income),
        vehicles_available=_optional_float(vehicles),
        mean_commute=_optional_float(commute),
        median_home_value=_optional_float(home_value),
    )


def _oews_from_row(row: sqlite3.Row | tuple[object, ...]) -> OewsWageRecord:
    area_code, area_name, soc, soc_title, mean_annual, median_annual, as_of = row
    return OewsWageRecord(
        area_code=str(area_code),
        area_name=str(area_name),
        soc=str(soc),
        soc_title=str(soc_title),
        mean_annual=_optional_float(mean_annual),
        median_annual=_optional_float(median_annual),
        as_of=str(as_of),
    )


def _ev_from_row(row: sqlite3.Row | tuple[object, ...]) -> EvZipRecord:
    zip_code, state, bev, phev, fcev, total_ldv, as_of, source = row
    return EvZipRecord(
        zip_code=str(zip_code),
        state=str(state),
        bev=_optional_int(bev),
        phev=_optional_int(phev),
        fcev=_optional_int(fcev),
        total_ldv=_optional_int(total_ldv),
        as_of=str(as_of),
        source=str(source),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Expected a number from SQLite, got {value!r}.")
    return float(value)
