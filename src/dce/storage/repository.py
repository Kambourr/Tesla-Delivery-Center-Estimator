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
import zlib
from collections.abc import Sequence
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
    median_gross_rent: float | None = None


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
        "mean_commute, median_home_value, households, median_gross_rent FROM zcta_acs "
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
            mean_commute, median_home_value, households, median_gross_rent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zcta, year) DO UPDATE SET
            population = excluded.population,
            median_hh_income = excluded.median_hh_income,
            vehicles_available = excluded.vehicles_available,
            mean_commute = excluded.mean_commute,
            median_home_value = excluded.median_home_value,
            households = excluded.households,
            median_gross_rent = excluded.median_gross_rent
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
            record.median_gross_rent,
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
    (
        zcta,
        year,
        population,
        income,
        vehicles,
        commute,
        home_value,
        households,
        gross_rent,
    ) = row
    return ZctaAcsRecord(
        zcta=str(zcta),
        year=_required_int(year),
        population=_optional_float(population),
        median_hh_income=_optional_float(income),
        vehicles_available=_optional_float(vehicles),
        mean_commute=_optional_float(commute),
        median_home_value=_optional_float(home_value),
        households=_optional_float(households),
        median_gross_rent=_optional_float(gross_rent),
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
    land_sqmi: float | None = None


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
        "SELECT zcta, lat, lon, vintage, as_of, land_sqmi FROM zcta_centroid "
        "WHERE zcta = ? AND vintage = ?"
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
        INSERT INTO zcta_centroid (zcta, lat, lon, vintage, as_of, land_sqmi)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(zcta, vintage) DO UPDATE SET
            lat = excluded.lat,
            lon = excluded.lon,
            as_of = excluded.as_of,
            land_sqmi = excluded.land_sqmi
        """,
        (record.zcta, record.lat, record.lon, record.vintage, record.as_of, record.land_sqmi),
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
    zcta, lat, lon, vintage, as_of, land_sqmi = row
    return ZctaCentroidRecord(
        zcta=str(zcta),
        lat=_required_float(lat),
        lon=_required_float(lon),
        vintage=str(vintage),
        as_of=str(as_of),
        land_sqmi=_optional_float(land_sqmi),
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


@dataclass(frozen=True)
class ZipCountyRecord:
    """One ``zip_county`` row. ``tot_ratio`` is the land share for a ZCTA."""

    zip_code: str
    county_fips: str
    state: str
    tot_ratio: float
    county_name: str = ""
    as_of: str | None = None


@dataclass(frozen=True)
class ZipCbsaRecord:
    """One ``zip_cbsa`` row. ``cbsa`` may be a metropolitan division."""

    zip_code: str
    cbsa: str
    tot_ratio: float
    cbsa_name: str = ""
    as_of: str | None = None


@dataclass(frozen=True)
class ZipZctaRecord:
    """One ``zip_zcta`` row."""

    zip_code: str
    zcta: str
    tot_ratio: float = 1.0


@dataclass(frozen=True)
class RentCbsaRecord:
    """One industrial asking-rent seed row."""

    cbsa: str
    property_type: str
    rent_psf_year: float
    as_of: str
    citation: str
    broker: str
    fetched_at: str | None = None


@dataclass(frozen=True)
class RentMarketRecord:
    """One broker market-report asking rent for a county or CBSA.

    ``rent_psf_year`` is the annual NNN equivalent; ``reported_*`` is the
    figure as printed.
    """

    geography_level: str
    geography_id: str
    market: str
    submarket: str
    property_type: str
    rent_psf_year: float
    reported_rent: float
    reported_unit: str
    reported_basis: str
    source: str
    report: str
    quarter: str
    as_of: str
    url: str
    note: str
    fetched_at: str | None = None


@dataclass(frozen=True)
class RentZipObsRecord:
    """One ZIP rent observation, usually a GSA lease summary."""

    zip_code: str
    property_type: str
    rent_psf_year: float
    as_of: str
    source: str
    citation: str
    n_leases: int | None = None


@dataclass(frozen=True)
class RentModelRecord:
    """The frozen ACS adjustment. ``formula_json`` holds the exponents."""

    model_id: str
    formula_json: str
    trained_on: str
    as_of: str


@dataclass(frozen=True)
class RentCacheRecord:
    """The last ``resolve_rent`` result for a ZIP."""

    zip_code: str
    rent_psf_year: float
    property_type: str
    tier: str
    confidence: str
    as_of: str
    components_json: str
    resolved_at: str
    citation: str


@dataclass(frozen=True)
class SafmrRecord:
    """HUD Small Area FMR, 2-bedroom, dollars per month."""

    zip_code: str
    rent_2br_month: float
    as_of: str
    citation: str


def replace_zip_geography(
    conn: sqlite3.Connection,
    counties: Sequence[ZipCountyRecord],
    cbsas: Sequence[ZipCbsaRecord],
    zctas: Sequence[ZipZctaRecord],
) -> None:
    """Replace the ZIP crosswalk tables in one transaction."""
    if not counties or not zctas:
        raise ValueError("Refusing to replace the ZIP crosswalk with no rows.")
    conn.execute("DELETE FROM zip_county")
    conn.execute("DELETE FROM zip_cbsa")
    conn.execute("DELETE FROM zip_zcta")
    conn.executemany(
        """
        INSERT INTO zip_county (
            zip, county_fips, state, res_ratio, bus_ratio, oth_ratio, tot_ratio, as_of, county_name
        ) VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, ?)
        """,
        [
            (row.zip_code, row.county_fips, row.state, row.tot_ratio, row.as_of, row.county_name)
            for row in counties
        ],
    )
    conn.executemany(
        """
        INSERT INTO zip_cbsa (zip, cbsa, res_ratio, bus_ratio, oth_ratio, tot_ratio, as_of, cbsa_name)
        VALUES (?, ?, NULL, NULL, NULL, ?, ?, ?)
        """,
        [(row.zip_code, row.cbsa, row.tot_ratio, row.as_of, row.cbsa_name) for row in cbsas],
    )
    conn.executemany(
        "INSERT INTO zip_zcta (zip, zcta, tot_ratio) VALUES (?, ?, ?)",
        [(row.zip_code, row.zcta, row.tot_ratio) for row in zctas],
    )
    conn.commit()


def list_zip_counties(conn: sqlite3.Connection, zip_code: str) -> tuple[ZipCountyRecord, ...]:
    """Return county rows for one ZIP, highest land share first."""
    query = (
        "SELECT zip, county_fips, state, tot_ratio, county_name, as_of FROM zip_county "
        "WHERE zip = ? ORDER BY tot_ratio DESC, county_fips"
    )
    return tuple(_zip_county_from_row(row) for row in conn.execute(query, (zip_code,)))


def list_zip_cbsas(conn: sqlite3.Connection, zip_code: str) -> tuple[ZipCbsaRecord, ...]:
    """Return CBSA rows for one ZIP, highest land share first."""
    query = (
        "SELECT zip, cbsa, tot_ratio, cbsa_name, as_of FROM zip_cbsa "
        "WHERE zip = ? ORDER BY tot_ratio DESC, cbsa"
    )
    return tuple(_zip_cbsa_from_row(row) for row in conn.execute(query, (zip_code,)))


def list_zip_zctas(conn: sqlite3.Connection, zip_code: str) -> tuple[ZipZctaRecord, ...]:
    """Return ZCTA rows for one ZIP."""
    query = "SELECT zip, zcta, tot_ratio FROM zip_zcta WHERE zip = ? ORDER BY tot_ratio DESC, zcta"
    return tuple(_zip_zcta_from_row(row) for row in conn.execute(query, (zip_code,)))


def replace_zcta_centroids(
    conn: sqlite3.Connection, rows: Sequence[ZctaCentroidRecord], *, vintage: str
) -> None:
    """Replace centroids for one gazetteer vintage."""
    if not rows:
        raise ValueError("Refusing to replace centroids with no rows.")
    conn.execute("DELETE FROM zcta_centroid WHERE vintage = ?", (vintage,))
    conn.executemany(
        """
        INSERT INTO zcta_centroid (zcta, lat, lon, vintage, as_of, land_sqmi)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [(row.zcta, row.lat, row.lon, row.vintage, row.as_of, row.land_sqmi) for row in rows],
    )
    conn.commit()


def replace_zcta_acs_year(
    conn: sqlite3.Connection, rows: Sequence[ZctaAcsRecord], *, year: int
) -> None:
    """Replace ACS rows for one year."""
    if not rows:
        raise ValueError("Refusing to replace ACS rows with no rows.")
    conn.execute("DELETE FROM zcta_acs WHERE year = ?", (year,))
    conn.executemany(
        """
        INSERT INTO zcta_acs (
            zcta, year, population, median_hh_income, vehicles_available,
            mean_commute, median_home_value, households, median_gross_rent
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.zcta,
                row.year,
                row.population,
                row.median_hh_income,
                row.vehicles_available,
                row.mean_commute,
                row.median_home_value,
                row.households,
                row.median_gross_rent,
            )
            for row in rows
        ],
    )
    conn.commit()


def get_latest_zcta_acs(conn: sqlite3.Connection, zcta: str) -> ZctaAcsRecord | None:
    """Return the newest ACS row for a ZCTA."""
    query = (
        "SELECT zcta, year, population, median_hh_income, vehicles_available, "
        "mean_commute, median_home_value, households, median_gross_rent FROM zcta_acs "
        "WHERE zcta = ? ORDER BY year DESC LIMIT 1"
    )
    row = conn.execute(query, (zcta,)).fetchone()
    if row is None:
        return None
    return _zcta_from_row(row)


def latest_acs_year(conn: sqlite3.Connection) -> int | None:
    """Return the newest year stored in ``zcta_acs``, or ``None`` when it is empty."""
    row = conn.execute("SELECT MAX(year) FROM zcta_acs").fetchone()
    if row is None or row[0] is None:
        return None
    return int(row[0])


def acs_positive_rents_for_county(
    conn: sqlite3.Connection, county_fips: str, year: int
) -> tuple[float, ...]:
    """Return positive ZCTA median gross rents whose dominant county is ``county_fips``."""
    query = (
        "SELECT a.median_gross_rent FROM zcta_acs AS a "
        "JOIN zip_county AS k ON k.zip = a.zcta "
        "WHERE a.year = ? AND a.median_gross_rent > 0 AND k.county_fips = ? "
        "AND NOT EXISTS ("
        "SELECT 1 FROM zip_county AS other WHERE other.zip = k.zip AND ("
        "other.tot_ratio > k.tot_ratio OR "
        "(other.tot_ratio = k.tot_ratio AND other.county_fips < k.county_fips)"
        "))"
    )
    return tuple(float(row[0]) for row in conn.execute(query, (year, county_fips)))


def acs_positive_rents_for_state(
    conn: sqlite3.Connection, state: str, year: int
) -> tuple[float, ...]:
    """Return positive ZCTA median gross rents whose dominant county is in ``state``."""
    query = (
        "SELECT a.median_gross_rent FROM zcta_acs AS a "
        "JOIN zip_county AS k ON k.zip = a.zcta "
        "WHERE a.year = ? AND a.median_gross_rent > 0 AND k.state = ? "
        "AND NOT EXISTS ("
        "SELECT 1 FROM zip_county AS other WHERE other.zip = k.zip AND ("
        "other.tot_ratio > k.tot_ratio OR "
        "(other.tot_ratio = k.tot_ratio AND other.county_fips < k.county_fips)"
        "))"
    )
    return tuple(float(row[0]) for row in conn.execute(query, (year, state)))


def acs_positive_rents_national(conn: sqlite3.Connection, year: int) -> tuple[float, ...]:
    """Return positive ZCTA median gross rents, one per ZCTA that is its own ZIP."""
    query = (
        "SELECT a.median_gross_rent FROM zcta_acs AS a "
        "WHERE a.year = ? AND a.median_gross_rent > 0 AND EXISTS ("
        "SELECT 1 FROM zip_zcta AS z WHERE z.zcta = a.zcta AND z.zip = z.zcta)"
    )
    return tuple(float(row[0]) for row in conn.execute(query, (year,)))


def acs_positive_values_for_cbsa(
    conn: sqlite3.Connection, cbsa: str, year: int, column: str
) -> tuple[float, ...]:
    """Return one ACS measure for ZCTAs whose dominant CBSA is ``cbsa``.

    ``column`` is a fixed ACS measure name. ZIPs that are not their own ZCTA
    are left out so a post-office box is not a second copy of the same rent.
    """
    allowed = {
        "median_gross_rent",
        "median_hh_income",
        "median_home_value",
        "population",
        "households",
    }
    if column not in allowed:
        raise ValueError(f"ACS column is not a rent-model measure: {column}.")
    query = (
        f"SELECT a.{column} FROM zcta_acs AS a "
        "JOIN zip_zcta AS z ON z.zcta = a.zcta AND z.zip = z.zcta "
        "JOIN zip_cbsa AS c ON c.zip = z.zip "
        f"WHERE c.cbsa = ? AND a.year = ? AND a.{column} > 0"
    )
    return tuple(float(row[0]) for row in conn.execute(query, (cbsa, year)))


def cbsas_for_state(conn: sqlite3.Connection, state: str) -> tuple[str, ...]:
    """Return distinct CBSA codes that appear on ZIPs in ``state``."""
    query = (
        "SELECT DISTINCT c.cbsa FROM zip_cbsa AS c "
        "JOIN zip_county AS k ON k.zip = c.zip "
        "WHERE k.state = ? ORDER BY c.cbsa"
    )
    return tuple(str(row[0]) for row in conn.execute(query, (state,)))


def upsert_oews_wages(conn: sqlite3.Connection, rows: Sequence[OewsWageRecord]) -> None:
    """Insert or replace many OEWS rows in one transaction."""
    conn.executemany(
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
        [
            (
                row.area_code,
                row.area_name,
                row.soc,
                row.soc_title,
                row.mean_annual,
                row.median_annual,
                row.as_of,
            )
            for row in rows
        ],
    )
    conn.commit()


def list_oews_wages(conn: sqlite3.Connection, area_code: str) -> tuple[OewsWageRecord, ...]:
    """Return every SOC for an area at that area's newest ``as_of``."""
    query = (
        "SELECT area_code, area_name, soc, soc_title, mean_annual, median_annual, as_of "
        "FROM oews_wage WHERE area_code = ? AND as_of = ("
        "SELECT MAX(as_of) FROM oews_wage WHERE area_code = ?"
        ") ORDER BY soc"
    )
    return tuple(_oews_from_row(row) for row in conn.execute(query, (area_code, area_code)))


def replace_rent_cbsa(conn: sqlite3.Connection, rows: Sequence[RentCbsaRecord]) -> None:
    """Replace the broker industrial seed."""
    conn.execute("DELETE FROM rent_cbsa")
    conn.executemany(
        """
        INSERT INTO rent_cbsa (
            cbsa, property_type, rent_psf_year, as_of, citation, broker, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.cbsa,
                row.property_type,
                row.rent_psf_year,
                row.as_of,
                row.citation,
                row.broker,
                row.fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def list_rent_cbsa(conn: sqlite3.Connection, cbsa: str) -> tuple[RentCbsaRecord, ...]:
    """Return seed rows for one CBSA, newest ``as_of`` first. Industrial before other types."""
    query = (
        "SELECT cbsa, property_type, rent_psf_year, as_of, citation, broker, fetched_at "
        "FROM rent_cbsa WHERE cbsa = ? ORDER BY as_of DESC, "
        "CASE property_type WHEN 'industrial' THEN 0 WHEN 'flex' THEN 1 ELSE 2 END"
    )
    return tuple(_rent_cbsa_from_row(row) for row in conn.execute(query, (cbsa,)))


def list_rent_cbsa_for_codes(
    conn: sqlite3.Connection, cbsas: Sequence[str]
) -> tuple[RentCbsaRecord, ...]:
    """Return the newest industrial row for each requested CBSA that has one."""
    if not cbsas:
        return ()
    placeholders = ", ".join("?" for _ in cbsas)
    query = (
        "SELECT cbsa, property_type, rent_psf_year, as_of, citation, broker, fetched_at "
        f"FROM rent_cbsa WHERE cbsa IN ({placeholders}) AND property_type = 'industrial' "
        "ORDER BY cbsa, as_of DESC"
    )
    seen: set[str] = set()
    rows: list[RentCbsaRecord] = []
    for raw in conn.execute(query, tuple(cbsas)):
        record = _rent_cbsa_from_row(raw)
        if record.cbsa in seen:
            continue
        seen.add(record.cbsa)
        rows.append(record)
    return tuple(rows)


_RENT_MARKET_COLUMNS = (
    "geography_level, geography_id, market, submarket, property_type, rent_psf_year, "
    "reported_rent, reported_unit, reported_basis, source, report, quarter, as_of, url, "
    "note, fetched_at"
)


def replace_rent_market(conn: sqlite3.Connection, rows: Sequence[RentMarketRecord]) -> None:
    """Replace every broker market rent row in one transaction."""
    conn.execute("DELETE FROM rent_market")
    conn.executemany(
        f"INSERT INTO rent_market ({_RENT_MARKET_COLUMNS}) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                row.geography_level,
                row.geography_id,
                row.market,
                row.submarket,
                row.property_type,
                row.rent_psf_year,
                row.reported_rent,
                row.reported_unit,
                row.reported_basis,
                row.source,
                row.report,
                row.quarter,
                row.as_of,
                row.url,
                row.note,
                row.fetched_at,
            )
            for row in rows
        ],
    )
    conn.commit()


def get_rent_market(
    conn: sqlite3.Connection, geography_level: str, geography_id: str
) -> RentMarketRecord | None:
    """Return the broker market rent for one county or CBSA, or ``None``."""
    row = conn.execute(
        f"SELECT {_RENT_MARKET_COLUMNS} FROM rent_market "
        "WHERE geography_level = ? AND geography_id = ?",
        (geography_level, geography_id),
    ).fetchone()
    return None if row is None else _rent_market_from_row(row)


def list_rent_market(conn: sqlite3.Connection) -> tuple[RentMarketRecord, ...]:
    """Return every broker market rent row, ordered by level and id."""
    query = f"SELECT {_RENT_MARKET_COLUMNS} FROM rent_market ORDER BY geography_level, geography_id"
    return tuple(_rent_market_from_row(row) for row in conn.execute(query))


def list_rent_zip_obs_for_zips(
    conn: sqlite3.Connection, zip_codes: Sequence[str], source: str
) -> tuple[RentZipObsRecord, ...]:
    """Return observations for these ZIPs and one source."""
    if not zip_codes:
        return ()
    placeholders = ", ".join("?" for _ in zip_codes)
    query = (
        "SELECT zip, property_type, rent_psf_year, as_of, source, citation, n_leases "
        f"FROM rent_zip_obs WHERE source = ? AND zip IN ({placeholders})"
    )
    return tuple(_rent_obs_from_row(row) for row in conn.execute(query, (source, *zip_codes)))


def zips_in_county(conn: sqlite3.Connection, county_fips: str) -> tuple[str, ...]:
    """Return ZIPs that touch a county."""
    query = "SELECT zip FROM zip_county WHERE county_fips = ? ORDER BY zip"
    return tuple(str(row[0]) for row in conn.execute(query, (county_fips,)))


def upsert_rent_model(conn: sqlite3.Connection, record: RentModelRecord) -> None:
    """Insert or replace one coefficient row."""
    conn.execute(
        """
        INSERT INTO rent_model_coeffs (model_id, formula_json, trained_on, as_of)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(model_id) DO UPDATE SET
            formula_json = excluded.formula_json,
            trained_on = excluded.trained_on,
            as_of = excluded.as_of
        """,
        (record.model_id, record.formula_json, record.trained_on, record.as_of),
    )
    conn.commit()


def get_rent_model(conn: sqlite3.Connection, model_id: str) -> RentModelRecord | None:
    """Return one coefficient row."""
    query = (
        "SELECT model_id, formula_json, trained_on, as_of FROM rent_model_coeffs WHERE model_id = ?"
    )
    row = conn.execute(query, (model_id,)).fetchone()
    if row is None:
        return None
    model_id_value, formula_json, trained_on, as_of = row
    return RentModelRecord(
        model_id=str(model_id_value),
        formula_json=str(formula_json),
        trained_on=str(trained_on),
        as_of=str(as_of),
    )


def upsert_rent_cache(conn: sqlite3.Connection, record: RentCacheRecord) -> None:
    """Insert or replace the resolved rent for one ZIP."""
    conn.execute(
        """
        INSERT INTO rent_resolved_cache (
            zip, rent_psf_year, property_type, tier, confidence, as_of,
            components_json, resolved_at, citation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zip) DO UPDATE SET
            rent_psf_year = excluded.rent_psf_year,
            property_type = excluded.property_type,
            tier = excluded.tier,
            confidence = excluded.confidence,
            as_of = excluded.as_of,
            components_json = excluded.components_json,
            resolved_at = excluded.resolved_at,
            citation = excluded.citation
        """,
        (
            record.zip_code,
            record.rent_psf_year,
            record.property_type,
            record.tier,
            record.confidence,
            record.as_of,
            record.components_json,
            record.resolved_at,
            record.citation,
        ),
    )
    conn.commit()


def upsert_safmr(conn: sqlite3.Connection, record: SafmrRecord) -> None:
    """Insert or replace one Small Area FMR row."""
    conn.execute(
        """
        INSERT INTO rent_safmr (zip, rent_2br_month, as_of, citation)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(zip, as_of) DO UPDATE SET
            rent_2br_month = excluded.rent_2br_month,
            citation = excluded.citation
        """,
        (record.zip_code, record.rent_2br_month, record.as_of, record.citation),
    )
    conn.commit()


def get_latest_safmr(conn: sqlite3.Connection, zip_code: str) -> SafmrRecord | None:
    """Return the newest 2-bedroom SAFMR for a ZIP."""
    query = (
        "SELECT zip, rent_2br_month, as_of, citation FROM rent_safmr "
        "WHERE zip = ? ORDER BY as_of DESC LIMIT 1"
    )
    row = conn.execute(query, (zip_code,)).fetchone()
    if row is None:
        return None
    zip_value, rent, as_of, citation = row
    return SafmrRecord(
        zip_code=str(zip_value),
        rent_2br_month=_required_float(rent),
        as_of=str(as_of),
        citation=str(citation),
    )


def replace_zev_sales(
    conn: sqlite3.Connection,
    zip_rows: Sequence[ZevZipSalesRecord],
    county_rows: Sequence[ZevCountySalesRecord],
) -> None:
    """Replace stored CEC sales. ``dmv`` and ``fallback`` rows are left in place."""
    if not zip_rows and not county_rows:
        raise ValueError("Refusing to replace CEC sales with no rows.")
    conn.execute("DELETE FROM zev_sales_zip WHERE source = 'cec'")
    conn.execute("DELETE FROM zev_sales_county WHERE source = 'cec'")
    conn.executemany(
        """
        INSERT INTO zev_sales_zip (
            zip, state, data_year, quarter, fuel_type, vehicles, as_of, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.zip_code,
                row.state,
                row.data_year,
                row.quarter,
                row.fuel_type,
                row.vehicles,
                row.as_of,
                row.source,
            )
            for row in zip_rows
        ],
    )
    conn.executemany(
        """
        INSERT INTO zev_sales_county (
            county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.county,
                row.state,
                row.data_year,
                row.quarter,
                row.fuel_type,
                row.make,
                row.vehicles,
                row.as_of,
                row.source,
            )
            for row in county_rows
        ],
    )
    conn.commit()


def list_zev_zip_year(
    conn: sqlite3.Connection, zip_code: str, *, source: str = "cec"
) -> tuple[ZevZipSalesRecord, ...]:
    """Return ZIP sales for the newest year stored for that ZIP and source."""
    query = (
        "SELECT zip, state, data_year, quarter, fuel_type, vehicles, as_of, source "
        "FROM zev_sales_zip WHERE zip = ? AND source = ? AND data_year = ("
        "SELECT MAX(data_year) FROM zev_sales_zip WHERE zip = ? AND source = ?"
        ") ORDER BY quarter, fuel_type"
    )
    return tuple(
        _zev_zip_from_row(row) for row in conn.execute(query, (zip_code, source, zip_code, source))
    )


def list_zip_counties_all(conn: sqlite3.Connection) -> tuple[ZipCountyRecord, ...]:
    """Return every ZIP-county row."""
    query = (
        "SELECT zip, county_fips, state, tot_ratio, county_name, as_of FROM zip_county "
        "ORDER BY zip, tot_ratio DESC, county_fips"
    )
    return tuple(_zip_county_from_row(row) for row in conn.execute(query))


def list_zip_cbsas_all(conn: sqlite3.Connection) -> tuple[ZipCbsaRecord, ...]:
    """Return every ZIP-CBSA row."""
    query = (
        "SELECT zip, cbsa, tot_ratio, cbsa_name, as_of FROM zip_cbsa "
        "ORDER BY zip, tot_ratio DESC, cbsa"
    )
    return tuple(_zip_cbsa_from_row(row) for row in conn.execute(query))


def list_zip_zctas_all(conn: sqlite3.Connection) -> tuple[ZipZctaRecord, ...]:
    """Return every ZIP-ZCTA row."""
    query = "SELECT zip, zcta, tot_ratio FROM zip_zcta ORDER BY zip, tot_ratio DESC, zcta"
    return tuple(_zip_zcta_from_row(row) for row in conn.execute(query))


def list_zcta_acs_year(conn: sqlite3.Connection, year: int) -> tuple[ZctaAcsRecord, ...]:
    """Return every ACS row for one year."""
    query = (
        "SELECT zcta, year, population, median_hh_income, vehicles_available, "
        "mean_commute, median_home_value, households, median_gross_rent FROM zcta_acs "
        "WHERE year = ?"
    )
    return tuple(_zcta_from_row(row) for row in conn.execute(query, (year,)))


def list_zcta_centroids(conn: sqlite3.Connection, vintage: str) -> tuple[ZctaCentroidRecord, ...]:
    """Return every centroid for one gazetteer vintage."""
    query = "SELECT zcta, lat, lon, vintage, as_of, land_sqmi FROM zcta_centroid WHERE vintage = ?"
    return tuple(_centroid_from_row(row) for row in conn.execute(query, (vintage,)))


def list_zev_zip_sales(
    conn: sqlite3.Connection, *, source: str = "cec"
) -> tuple[ZevZipSalesRecord, ...]:
    """Return every stored ZIP sales row for one source."""
    query = (
        "SELECT zip, state, data_year, quarter, fuel_type, vehicles, as_of, source "
        "FROM zev_sales_zip WHERE source = ?"
    )
    return tuple(_zev_zip_from_row(row) for row in conn.execute(query, (source,)))


def list_zev_county_sales(
    conn: sqlite3.Connection, *, source: str = "cec"
) -> tuple[ZevCountySalesRecord, ...]:
    """Return every stored county sales row for one source."""
    query = (
        "SELECT county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source "
        "FROM zev_sales_county WHERE source = ?"
    )
    return tuple(_zev_county_from_row(row) for row in conn.execute(query, (source,)))


@dataclass(frozen=True)
class ZipResultRecord:
    """One precomputed estimate, or the reason that ZIP could not be estimated."""

    zip_code: str
    model_version: str
    inputs_hash: str
    status: str
    reason: str | None
    payload_json: str
    computed_at: str
    elapsed_ms: float | None = None


def encode_zip_payload(payload_json: str) -> bytes:
    """Compress one canonical JSON document for ``zip_result.payload_json``.

    zlib level 9 is deterministic for the same bytes. The read path expands
    this back to the JSON string.
    """
    return zlib.compress(payload_json.encode("utf-8"), level=9)


def decode_zip_payload(value: object) -> str:
    """Return the JSON text stored in ``zip_result.payload_json``.

    New rows are zlib bytes. A row copied forward from schema version 6 is
    still plain JSON text, or UTF-8 bytes of that text.
    """
    if isinstance(value, memoryview):
        value = bytes(value)
    if isinstance(value, bytes):
        if value.startswith(b"\x78"):
            return zlib.decompress(value).decode("utf-8")
        return value.decode("utf-8")
    return str(value)


def upsert_zip_results(conn: sqlite3.Connection, rows: Sequence[ZipResultRecord]) -> None:
    """Insert or replace precomputed rows in one transaction."""
    conn.executemany(
        """
        INSERT INTO zip_result (
            zip, model_version, inputs_hash, status, reason, payload_json, computed_at, elapsed_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zip) DO UPDATE SET
            model_version = excluded.model_version,
            inputs_hash = excluded.inputs_hash,
            status = excluded.status,
            reason = excluded.reason,
            payload_json = excluded.payload_json,
            computed_at = excluded.computed_at,
            elapsed_ms = excluded.elapsed_ms
        """,
        [
            (
                row.zip_code,
                row.model_version,
                row.inputs_hash,
                row.status,
                row.reason,
                encode_zip_payload(row.payload_json),
                row.computed_at,
                row.elapsed_ms,
            )
            for row in rows
        ],
    )
    conn.commit()


def get_zip_result_row(conn: sqlite3.Connection, zip_code: str) -> ZipResultRecord | None:
    """Return the stored result for one ZIP, or ``None``."""
    query = (
        "SELECT zip, model_version, inputs_hash, status, reason, payload_json, "
        "computed_at, elapsed_ms FROM zip_result WHERE zip = ?"
    )
    row = conn.execute(query, (zip_code,)).fetchone()
    if row is None:
        return None
    return _zip_result_from_row(row)


def get_zip_result_rows(
    conn: sqlite3.Connection, zip_codes: Sequence[str]
) -> tuple[ZipResultRecord, ...]:
    """Return stored results for the requested ZIPs. Missing ZIPs are omitted."""
    if not zip_codes:
        return ()
    found: list[ZipResultRecord] = []
    for code in zip_codes:
        row = get_zip_result_row(conn, code)
        if row is not None:
            found.append(row)
    return tuple(found)


def national_seed_loaded(conn: sqlite3.Connection) -> bool:
    """Return whether the nationwide ZIP seed is already in this database.

    The thresholds match ``data/seed/coverage.json`` with some room, so a
    partial demo database is reloaded and a full one is not.
    """
    counts = {
        "zip_zcta": 40_000,
        "zcta_acs": 30_000,
        "zev_sales_zip": 7_000,
        "oews_wage": 300,
    }
    for table, minimum in counts.items():
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None or int(row[0]) < minimum:
            return False
    return True


def count_zip_results(conn: sqlite3.Connection) -> dict[str, int]:
    """Return how many stored rows are ``ok`` and how many are ``error``.

    Statuses that are absent are reported as zero so a report can print both.
    """
    counts = {"ok": 0, "error": 0}
    for status, count in conn.execute("SELECT status, COUNT(*) FROM zip_result GROUP BY status"):
        counts[str(status)] = int(count)
    return counts


def list_fresh_zip_results(
    conn: sqlite3.Connection,
    *,
    model_version: str,
    inputs_hash: str,
    include_errors: bool,
) -> set[str]:
    """Return ZIPs whose stored row matches this model version and inputs hash.

    Error rows are included only when ``include_errors`` is true. A resume
    then leaves a failed ZIP in place instead of trying it again.
    """
    if include_errors:
        query = (
            "SELECT zip FROM zip_result WHERE model_version = ? AND inputs_hash = ? "
            "AND status IN ('ok', 'error')"
        )
    else:
        query = (
            "SELECT zip FROM zip_result WHERE model_version = ? AND inputs_hash = ? "
            "AND status = 'ok'"
        )
    return {str(row[0]) for row in conn.execute(query, (model_version, inputs_hash))}


def list_zev_county_year(
    conn: sqlite3.Connection, county: str, *, source: str = "cec"
) -> tuple[ZevCountySalesRecord, ...]:
    """Return county sales for the newest year stored for that county name."""
    query = (
        "SELECT county, state, data_year, quarter, fuel_type, make, vehicles, as_of, source "
        "FROM zev_sales_county WHERE county = ? AND source = ? AND data_year = ("
        "SELECT MAX(data_year) FROM zev_sales_county WHERE county = ? AND source = ?"
        ") ORDER BY quarter, make"
    )
    return tuple(
        _zev_county_from_row(row) for row in conn.execute(query, (county, source, county, source))
    )


def get_latest_ev_zip(conn: sqlite3.Connection, zip_code: str) -> EvZipRecord | None:
    """Return the newest vehicle-count row for a ZIP. ``cec`` wins over ``dmv`` over ``fallback``."""
    query = (
        "SELECT zip, state, bev, phev, fcev, total_ldv, as_of, source FROM ev_zip "
        "WHERE zip = ? ORDER BY as_of DESC, "
        "CASE source WHEN 'cec' THEN 0 WHEN 'dmv' THEN 1 ELSE 2 END LIMIT 1"
    )
    row = conn.execute(query, (zip_code,)).fetchone()
    if row is None:
        return None
    return _ev_from_row(row)


def _zip_county_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZipCountyRecord:
    zip_code, county_fips, state, tot_ratio, county_name, as_of = row
    return ZipCountyRecord(
        zip_code=str(zip_code),
        county_fips=str(county_fips),
        state=str(state),
        tot_ratio=_required_float(tot_ratio),
        county_name="" if county_name is None else str(county_name),
        as_of=None if as_of is None else str(as_of),
    )


def _zip_cbsa_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZipCbsaRecord:
    zip_code, cbsa, tot_ratio, cbsa_name, as_of = row
    return ZipCbsaRecord(
        zip_code=str(zip_code),
        cbsa=str(cbsa),
        tot_ratio=_required_float(tot_ratio),
        cbsa_name="" if cbsa_name is None else str(cbsa_name),
        as_of=None if as_of is None else str(as_of),
    )


def _zip_result_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZipResultRecord:
    zip_code, model_version, inputs_hash, status, reason, payload, computed_at, elapsed = row
    return ZipResultRecord(
        zip_code=str(zip_code),
        model_version=str(model_version),
        inputs_hash=str(inputs_hash),
        status=str(status),
        reason=None if reason is None else str(reason),
        payload_json=decode_zip_payload(payload),
        computed_at=str(computed_at),
        elapsed_ms=_optional_float(elapsed),
    )


def _zip_zcta_from_row(row: sqlite3.Row | tuple[object, ...]) -> ZipZctaRecord:
    zip_code, zcta, tot_ratio = row
    return ZipZctaRecord(
        zip_code=str(zip_code),
        zcta=str(zcta),
        tot_ratio=1.0 if tot_ratio is None else _required_float(tot_ratio),
    )


def _rent_cbsa_from_row(row: sqlite3.Row | tuple[object, ...]) -> RentCbsaRecord:
    cbsa, property_type, rent, as_of, citation, broker, fetched_at = row
    return RentCbsaRecord(
        cbsa=str(cbsa),
        property_type=str(property_type),
        rent_psf_year=_required_float(rent),
        as_of=str(as_of),
        citation=str(citation),
        broker=str(broker),
        fetched_at=None if fetched_at is None else str(fetched_at),
    )


def _rent_market_from_row(row: sqlite3.Row | tuple[object, ...]) -> RentMarketRecord:
    (
        level,
        geo_id,
        market,
        submarket,
        property_type,
        rent,
        reported,
        unit,
        basis,
        source,
        report,
        quarter,
        as_of,
        url,
        note,
        fetched_at,
    ) = row
    return RentMarketRecord(
        geography_level=str(level),
        geography_id=str(geo_id),
        market=str(market),
        submarket=str(submarket),
        property_type=str(property_type),
        rent_psf_year=_required_float(rent),
        reported_rent=_required_float(reported),
        reported_unit=str(unit),
        reported_basis=str(basis),
        source=str(source),
        report=str(report),
        quarter=str(quarter),
        as_of=str(as_of),
        url=str(url),
        note=str(note),
        fetched_at=None if fetched_at is None else str(fetched_at),
    )


def _rent_obs_from_row(row: sqlite3.Row | tuple[object, ...]) -> RentZipObsRecord:
    zip_code, property_type, rent, as_of, source, citation, n_leases = row
    return RentZipObsRecord(
        zip_code=str(zip_code),
        property_type=str(property_type),
        rent_psf_year=_required_float(rent),
        as_of=str(as_of),
        source=str(source),
        citation=str(citation),
        n_leases=None if n_leases is None else _required_int(n_leases),
    )
