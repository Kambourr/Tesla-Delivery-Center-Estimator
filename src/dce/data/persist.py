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
from dce.data.ingest.delivery_centers import DeliveryCenter
from dce.data.ingest.zcta_gazetteer import ZctaCentroid
from dce.data.ingest.zev_sales import ZevCountySales, ZevSalesBatch, ZevZipSales
from dce.storage.repository import (
    DeliveryCenterRecord,
    EvZipRecord,
    OewsWageRecord,
    SourceRecord,
    ZctaAcsRecord,
    ZctaCentroidRecord,
    ZevCountySalesRecord,
    ZevZipSalesRecord,
    upsert_delivery_center,
    upsert_ev_zip,
    upsert_oews_wage,
    upsert_source,
    upsert_zcta_acs,
    upsert_zcta_centroid,
    upsert_zev_county_sales,
    upsert_zev_zip_sales,
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


def persist_delivery_centers(
    conn: sqlite3.Connection,
    rows: Sequence[DeliveryCenter],
    *,
    source_id: str,
    url: str,
    as_of: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    """Upsert delivery-center rows and one registry row for that snapshot."""
    if not rows:
        raise PersistError("Refusing to record a delivery-center source with no rows.")
    for row in rows:
        if row.as_of != as_of:
            raise PersistError(f"Center {row.center_id} as_of {row.as_of} does not match {as_of}.")
        upsert_delivery_center(conn, _delivery_center_record(row), commit=False)
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


def persist_zcta_centroids(
    conn: sqlite3.Connection,
    rows: Sequence[ZctaCentroid],
    *,
    source_id: str,
    url: str,
    as_of: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
    byte_count: int | None,
) -> None:
    """Upsert ZCTA centroids and one registry row for that gazetteer vintage."""
    if not rows:
        raise PersistError("Refusing to record a gazetteer source with no centroids.")
    for row in rows:
        if row.as_of != as_of:
            raise PersistError(f"ZCTA {row.zcta} as_of {row.as_of} does not match {as_of}.")
        upsert_zcta_centroid(conn, _centroid_record(row), commit=False)
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


def persist_zev_sales(
    conn: sqlite3.Connection,
    batch: ZevSalesBatch,
    *,
    source_id: str,
    fetched_at: str,
    ttl_days: int,
    license_note: str,
) -> None:
    """Upsert ZIP and county sales from one workbook and record its ``as_of``."""
    if not batch.zip_sales or not batch.county_sales:
        raise PersistError("Refusing to record a ZEV source with no sales rows.")
    for zip_row in batch.zip_sales:
        upsert_zev_zip_sales(conn, _zev_zip_record(zip_row), commit=False)
    for county_row in batch.county_sales:
        upsert_zev_county_sales(conn, _zev_county_record(county_row), commit=False)
    _write_source(
        conn,
        source_id=source_id,
        url=batch.source_url,
        as_of=batch.as_of,
        fetched_at=fetched_at,
        ttl_days=ttl_days,
        license_note=license_note,
        byte_count=batch.byte_count,
    )


def _delivery_center_record(row: DeliveryCenter) -> DeliveryCenterRecord:
    return DeliveryCenterRecord(
        center_id=row.center_id,
        name=row.name,
        address=row.address,
        city=row.city,
        state=row.state,
        zip_code=row.zip_code,
        lat=row.lat,
        lon=row.lon,
        location_type=row.location_type,
        as_of=row.as_of,
        coordinate_basis=row.coordinate_basis,
    )


def _centroid_record(row: ZctaCentroid) -> ZctaCentroidRecord:
    return ZctaCentroidRecord(
        zcta=row.zcta,
        lat=row.lat,
        lon=row.lon,
        vintage=row.vintage,
        as_of=row.as_of,
    )


def _zev_zip_record(row: ZevZipSales) -> ZevZipSalesRecord:
    return ZevZipSalesRecord(
        zip_code=row.zip_code,
        state=row.state,
        data_year=row.data_year,
        quarter=row.quarter,
        fuel_type=row.fuel_type,
        vehicles=row.vehicles,
        as_of=row.as_of,
        source=row.source,
    )


def _zev_county_record(row: ZevCountySales) -> ZevCountySalesRecord:
    return ZevCountySalesRecord(
        county=row.county,
        state=row.state,
        data_year=row.data_year,
        quarter=row.quarter,
        fuel_type=row.fuel_type,
        make=row.make,
        vehicles=row.vehicles,
        as_of=row.as_of,
        source=row.source,
    )


def _whole(value: float | None, *, what: str) -> int | None:
    if value is None:
        return None
    if not value.is_integer() or value < 0:
        raise PersistError(f"{what} must be a whole number >= 0, got {value!r}.")
    return int(value)
