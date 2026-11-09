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
    households: float | None = None


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
        "mean_commute, median_home_value, households FROM zcta_acs "
        "WHERE zcta = ? AND year = ?"
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
            mean_commute, median_home_value, households
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zcta, year) DO UPDATE SET
            population = excluded.population,
            median_hh_income = excluded.median_hh_income,
            vehicles_available = excluded.vehicles_available,
            mean_commute = excluded.mean_commute,
            median_home_value = excluded.median_home_value,
            households = excluded.households
        """,
        (
            record.zcta,
            record.year,
            record.population,
            record.median_hh_income,
            record.vehicles_available,
            record.mean_commute,
            record.median_home_value,
            record.households,
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
    zcta, year, population, income, vehicles, commute, home_value, households = row
    return ZctaAcsRecord(
        zcta=str(zcta),
        year=_required_int(year),
        population=_optional_float(population),
        median_hh_income=_optional_float(income),
        vehicles_available=_optional_float(vehicles),
        mean_commute=_optional_float(commute),
        median_home_value=_optional_float(home_value),
        households=_optional_float(households),
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
    return _required_float(value)


@dataclass(frozen=True)
class DeliveryCenterRecord:
    """One ``delivery_center`` row. ``as_of`` is ISO text. Coordinates are decimal degrees."""

    center_id: str
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    lat: float
    lon: float
    location_type: str
    as_of: str
    coordinate_basis: str


@dataclass(frozen=True)
class ZctaCentroidRecord:
    """One ``zcta_centroid`` row. ``vintage`` is the gazetteer year."""

    zcta: str
    lat: float
    lon: float
    vintage: str
    as_of: str


@dataclass(frozen=True)
class ZevZipSalesRecord:
    """One ``zev_sales_zip`` row. ``vehicles`` is a whole count. ``source`` is cec or fallback."""

    zip_code: str
    state: str
    data_year: int
    quarter: int
    fuel_type: str
    vehicles: int
    as_of: str
    source: str


@dataclass(frozen=True)
class ZevCountySalesRecord:
    """One ``zev_sales_county`` row. Models are already summed into ``vehicles``."""

    county: str
    state: str
    data_year: int
    quarter: int
    fuel_type: str
    make: str
    vehicles: int
    as_of: str
    source: str


def list_delivery_centers(conn: sqlite3.Connection, as_of: str) -> tuple[DeliveryCenterRecord, ...]:
    """Return every center for one snapshot date, ordered by ``center_id``."""
    query = (
        "SELECT center_id, name, address, city, state, zip, lat, lon, "
        "location_type, as_of, coordinate_basis "
        "FROM delivery_center WHERE as_of = ? ORDER BY center_id"
    )
    return tuple(_delivery_center_from_row(row) for row in conn.execute(query, (as_of,)))


def upsert_delivery_center(
    conn: sqlite3.Connection, record: DeliveryCenterRecord, *, commit: bool = True
) -> None:
    """Insert or replace one delivery-center row."""
    conn.execute(
        """
        INSERT INTO delivery_center (
            center_id, name, address, city, state, zip, lat, lon,
            location_type, as_of, coordinate_basis
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(center_id, as_of) DO UPDATE SET
            name = excluded.name,
            address = excluded.address,
            city = excluded.city,
            state = excluded.state,
            zip = excluded.zip,
            lat = excluded.lat,
            lon = excluded.lon,
            location_type = excluded.location_type,
            coordinate_basis = excluded.coordinate_basis
        """,
        (
            record.center_id,
            record.name,
            record.address,
            record.city,
            record.state,
            record.zip_code,
            record.lat,
            record.lon,
            record.location_type,
            record.as_of,
            record.coordinate_basis,
        ),
    )
    if commit:
        conn.commit()


def get_zcta_centroid(
    conn: sqlite3.Connection, zcta: str, vintage: str
) -> ZctaCentroidRecord | None:
    """Return one ZCTA internal point, or ``None`` when it was never stored."""
    query = (
        "SELECT zcta, lat, lon, vintage, as_of FROM zcta_centroid WHERE zcta = ? AND vintage = ?"
    )
    row = conn.execute(query, (zcta, vintage)).fetchone()
    if row is None:
        return None
    return _centroid_from_row(row)


def upsert_zcta_centroid(
    conn: sqlite3.Connection, record: ZctaCentroidRecord, *, commit: bool = True
) -> None:
    """Insert or replace one ZCTA centroid."""
    conn.execute(
        """
        INSERT INTO zcta_centroid (zcta, lat, lon, vintage, as_of)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(zcta, vintage) DO UPDATE SET
            lat = excluded.lat,
            lon = excluded.lon,
            as_of = excluded.as_of
        """,
        (record.zcta, record.lat, record.lon, record.vintage, record.as_of),
    )
    if commit:
        conn.commit()


def get_zev_zip_sales(
    conn: sqlite3.Connection,
    zip_code: str,
    data_year: int,
    quarter: int,
    fuel_type: str,
    source: str,
) -> ZevZipSalesRecord | None:
    """Return one ZIP sales row, or ``None`` when it was never stored."""
    query = (
        "SELECT zip, state, data_year, quarter, fuel_type, vehicles, as_of, source "
        "FROM zev_sales_zip WHERE zip = ? AND data_year = ? AND quarter = ? "
        "AND fuel_type = ? AND source = ?"
    )
    row = conn.execute(query, (zip_code, data_year, quarter, fuel_type, source)).fetchone()
    if row is None:
        return None
    return _zev_zip_from_row(row)


def upsert_zev_zip_sales(
    conn: sqlite3.Connection, record: ZevZipSalesRecord, *, commit: bool = True
) -> None:
    """Insert or replace one ZIP sales row."""
    conn.execute(
        """
        INSERT INTO zev_sales_zip (
            zip, state, data_year, quarter, fuel_type, vehicles, as_of, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zip, data_year, quarter, fuel_type, source) DO UPDATE SET
            state = excluded.state,
            vehicles = excluded.vehicles,
            as_of = excluded.as_of
        """,
        (
            record.zip_code,
            record.state,
            record.data_year,
            record.quarter,
            record.fuel_type,
            record.vehicles,
            record.as_of,
            record.source,
        ),
    )
    if commit:
        conn.commit()


def get_zev_county_sales(
    conn: sqlite3.Connection,
    county: str,
    data_year: int,
    quarter: int,
    fuel_type: str,
    make: str,
    source: str,
) -> ZevCountySalesRecord | None:
    """Return one county make row, or ``None`` when it was never stored."""
    query = (
        "SELECT county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source "
        "FROM zev_sales_county WHERE county = ? AND data_year = ? AND quarter = ? "
        "AND fuel_type = ? AND make = ? AND source = ?"
    )
    row = conn.execute(query, (county, data_year, quarter, fuel_type, make, source)).fetchone()
    if row is None:
        return None
    return _zev_county_from_row(row)


def upsert_zev_county_sales(
    conn: sqlite3.Connection, record: ZevCountySalesRecord, *, commit: bool = True
) -> None:
    """Insert or replace one county make row."""
    conn.execute(
        """
        INSERT INTO zev_sales_county (
            county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(county, data_year, quarter, fuel_type, make, source) DO UPDATE SET
            state = excluded.state,
            vehicles = excluded.vehicles,
            as_of = excluded.as_of
        """,
        (
            record.county,
            record.state,
            record.data_year,
            record.quarter,
            record.fuel_type,
            record.make,
            record.vehicles,
            record.as_of,
            record.source,
        ),
    )
    if commit:
        conn.commit()


def _delivery_center_from_row(row: sqlite3.Row | tuple[object, ...]) -> DeliveryCenterRecord:
    (
        center_id,
        name,
        address,
        city,
        state,
        zip_code,
        lat,
        lon,
        location_type,
        as_of,
        coordinate_basis,
    ) = row
    return DeliveryCenterRecord(
        center_id=str(center_id),
        name=str(name),
        address=str(address),
        city=str(city),
        state=str(state),
        zip_code=str(zip_code),
        lat=_required_float(lat),
        lon=_required_float(lon),
        location_type=str(location_type),
        as_of=str(as_of),
        coordinate_basis=str(coordinate_basis),
    )


def _centroid_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZctaCentroidRecord:
    zcta, lat, lon, vintage, as_of = row
    return ZctaCentroidRecord(
        zcta=str(zcta),
        lat=_required_float(lat),
        lon=_required_float(lon),
        vintage=str(vintage),
        as_of=str(as_of),
    )


def _zev_zip_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZevZipSalesRecord:
    zip_code, state, data_year, quarter, fuel_type, vehicles, as_of, source = row
    return ZevZipSalesRecord(
        zip_code=str(zip_code),
        state=str(state),
        data_year=_required_int(data_year),
        quarter=_required_int(quarter),
        fuel_type=str(fuel_type),
        vehicles=_required_int(vehicles),
        as_of=str(as_of),
        source=str(source),
    )


def _zev_county_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZevCountySalesRecord:
    county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source = row
    return ZevCountySalesRecord(
        county=str(county),
        state=str(state),
        data_year=_required_int(data_year),
        quarter=_required_int(quarter),
        fuel_type=str(fuel_type),
        make=str(make),
        vehicles=_required_int(vehicles),
        as_of=str(as_of),
        source=str(source),
    )


def _required_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Expected a number from SQLite, got {value!r}.")
    return float(value)
