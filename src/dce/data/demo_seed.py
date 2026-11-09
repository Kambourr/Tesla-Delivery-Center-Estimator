"""San Mateo demo load: fixtures by default, allowlisted refresh on request.

The fixture path reads ``data/demo/san_mateo`` and does not need Census, BLS,
or HUD keys. CI uses that path. ``refresh_san_mateo`` calls the ingest
fetchers. Census refresh needs ``CENSUS_API_KEY``. BLS and the DMV file do not.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from dce.config import DB_FILENAME, api_key, demo_data_dir, user_data_dir
from dce.data.ingest.bls_oews import (
    BLS_OEWS_SOURCE_ID,
    OEWS_SOC_AUTO_TECH,
    OEWS_TTL_DAYS,
    OewsWage,
    fetch_oews_wage,
    oews_area_for_cbsa,
    oews_dataset_url,
    oews_license_note,
    parse_oews_payload,
)
from dce.data.ingest.ca_ev import (
    CA_EV_DMV_SOURCE_ID,
    EV_TTL_DAYS,
    EvZipCount,
    aggregate_ev_records,
    dmv_dataset_url,
    ev_license_note,
    fetch_ev_zip,
)
from dce.data.ingest.census_acs import (
    ACS_DEMO_YEAR,
    ACS_TTL_DAYS,
    CENSUS_ACS_SOURCE_ID,
    CensusApiKeyError,
    ZctaAcs,
    acs_as_of,
    census_dataset_url,
    census_license_note,
    fetch_zcta_acs,
    parse_census_table,
)
from dce.data.persist import persist_ev_zip, persist_oews_wage, persist_zcta_acs
from dce.geo.resolve import resolve_zip

DEMO_ZIPS = ("94401", "94402", "94403", "94404")
_FETCHED_AT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"


@dataclass(frozen=True)
class DemoSeedCounts:
    """How many fact rows the demo load wrote."""

    acs_rows: int
    oews_rows: int
    ev_rows: int


class DemoSeedError(Exception):
    """The San Mateo demo file could not be loaded."""


def san_mateo_demo_dir() -> Path:
    """Return ``data/demo/san_mateo``."""
    return demo_data_dir() / "san_mateo"


def utc_now_stamp() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_san_mateo_demo(
    conn: sqlite3.Connection,
    demo_dir: Path | None = None,
    *,
    fetched_at: str | None = None,
) -> DemoSeedCounts:
    """Upsert the committed San Mateo fixtures. Does not use the network."""
    root = san_mateo_demo_dir() if demo_dir is None else demo_dir
    stamp = _require_stamp(fetched_at or utc_now_stamp())
    acs_rows = _load_acs(conn, root / "census_acs_2024.json", fetched_at=stamp)
    oews_rows = _load_oews(conn, root / "oews_may_2025.json", fetched_at=stamp)
    ev_rows = _load_ev(conn, root / "dmv_fuel_2024.json", fetched_at=stamp)
    return DemoSeedCounts(acs_rows=len(acs_rows), oews_rows=oews_rows, ev_rows=len(ev_rows))


def refresh_san_mateo(
    conn: sqlite3.Connection,
    *,
    fetched_at: str | None = None,
) -> DemoSeedCounts:
    """Fetch 94401–94404 from the allowlist and upsert them.

    Census is checked for a key before any request, so a missing key does not
    leave a partial OEWS or DMV write. Rows are fetched fully, then stored.
    """
    if api_key("CENSUS_API_KEY") is None:
        raise CensusApiKeyError(
            "Refreshing Census ACS needs CENSUS_API_KEY. "
            "Run the demo loader without --refresh to use the committed fixtures."
        )
    areas = {oews_area_for_cbsa(resolve_zip(zip_code).cbsa) for zip_code in DEMO_ZIPS}
    if len(areas) != 1:
        raise DemoSeedError("San Mateo demo ZIPs must share one OEWS metro.")
    area = next(iter(areas))
    acs_rows = [fetch_zcta_acs(zip_code, year=ACS_DEMO_YEAR) for zip_code in DEMO_ZIPS]
    wage = fetch_oews_wage(area, OEWS_SOC_AUTO_TECH)
    ev_rows = [fetch_ev_zip(zip_code) for zip_code in DEMO_ZIPS]
    stamp = _require_stamp(fetched_at or utc_now_stamp())
    _store_acs(
        conn, acs_rows, url=census_dataset_url(ACS_DEMO_YEAR), fetched_at=stamp, byte_count=None
    )
    _store_oews(conn, wage, url=oews_dataset_url(), fetched_at=stamp, byte_count=None)
    ev_as_of = ev_rows[0].as_of
    _store_ev(conn, ev_rows, as_of=ev_as_of, fetched_at=stamp, byte_count=None)
    return DemoSeedCounts(acs_rows=len(acs_rows), oews_rows=1, ev_rows=len(ev_rows))


def _load_acs(conn: sqlite3.Connection, path: Path, *, fetched_at: str) -> list[ZctaAcs]:
    payload, size = _read_object(path)
    year = _required_int(payload.get("year"), what=f"{path.name} year")
    as_of = _required_str(payload.get("as_of"), what=f"{path.name} as_of")
    if as_of != acs_as_of(year):
        raise DemoSeedError(f"{path.name} as_of {as_of} does not match ACS year {year}.")
    rows = parse_census_table(payload.get("table"), year=year)
    _require_zips(tuple(row.zcta for row in rows), what=path.name)
    _store_acs(
        conn,
        rows,
        url=_required_str(payload.get("dataset_url"), what=f"{path.name} dataset_url"),
        fetched_at=fetched_at,
        byte_count=size,
        license_note=_required_str(payload.get("license_note"), what=f"{path.name} license_note"),
        as_of=as_of,
    )
    return rows


def _load_oews(conn: sqlite3.Connection, path: Path, *, fetched_at: str) -> int:
    payload, size = _read_object(path)
    area_code = _required_str(payload.get("area_code"), what=f"{path.name} area_code")
    soc = _required_str(payload.get("soc"), what=f"{path.name} soc")
    wage = parse_oews_payload(
        payload.get("payload"),
        area_code=area_code,
        area_name=_required_str(payload.get("area_name"), what=f"{path.name} area_name"),
        soc=soc,
        soc_title=_required_str(payload.get("soc_title"), what=f"{path.name} soc_title"),
        mean_series_id=_required_str(
            payload.get("mean_series_id"), what=f"{path.name} mean_series_id"
        ),
        median_series_id=_required_str(
            payload.get("median_series_id"), what=f"{path.name} median_series_id"
        ),
    )
    expected_as_of = _required_str(payload.get("as_of"), what=f"{path.name} as_of")
    if wage.as_of != expected_as_of:
        raise DemoSeedError(f"{path.name} as_of {expected_as_of} does not match the BLS year.")
    _store_oews(
        conn,
        wage,
        url=_required_str(payload.get("dataset_url"), what=f"{path.name} dataset_url"),
        fetched_at=fetched_at,
        byte_count=size,
        license_note=_required_str(payload.get("license_note"), what=f"{path.name} license_note"),
    )
    return 1


def _load_ev(conn: sqlite3.Connection, path: Path, *, fetched_at: str) -> list[EvZipCount]:
    payload, size = _read_object(path)
    as_of = _required_str(payload.get("as_of"), what=f"{path.name} as_of")
    source = _required_str(payload.get("source"), what=f"{path.name} source")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        raise DemoSeedError(f"{path.name} records must be a list.")
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in raw_records:
        if not isinstance(item, dict):
            raise DemoSeedError(f"{path.name} has a record that is not an object.")
        zip_code = item.get("ZIP Code")
        if not isinstance(zip_code, str):
            raise DemoSeedError(f"{path.name} record is missing ZIP Code.")
        grouped.setdefault(zip_code, []).append(item)
    _require_zips(tuple(grouped), what=path.name)
    rows = [
        aggregate_ev_records(zip_code, grouped[zip_code], source=source) for zip_code in DEMO_ZIPS
    ]
    for row in rows:
        if row.as_of != as_of:
            raise DemoSeedError(f"{path.name} ZIP {row.zip_code} as_of does not match {as_of}.")
    _store_ev(
        conn,
        rows,
        as_of=as_of,
        fetched_at=fetched_at,
        byte_count=size,
        license_note=_required_str(payload.get("license_note"), what=f"{path.name} license_note"),
        url=_required_str(payload.get("dataset_url"), what=f"{path.name} dataset_url"),
    )
    return rows


def _store_acs(
    conn: sqlite3.Connection,
    rows: list[ZctaAcs],
    *,
    url: str,
    fetched_at: str,
    byte_count: int | None,
    license_note: str | None = None,
    as_of: str | None = None,
) -> None:
    vintage = rows[0].year
    persist_zcta_acs(
        conn,
        rows,
        source_id=CENSUS_ACS_SOURCE_ID,
        url=url,
        as_of=as_of or acs_as_of(vintage),
        fetched_at=fetched_at,
        ttl_days=ACS_TTL_DAYS,
        license_note=license_note or census_license_note(),
        byte_count=byte_count,
    )


def _store_oews(
    conn: sqlite3.Connection,
    wage: OewsWage,
    *,
    url: str,
    fetched_at: str,
    byte_count: int | None,
    license_note: str | None = None,
) -> None:
    persist_oews_wage(
        conn,
        wage,
        source_id=BLS_OEWS_SOURCE_ID,
        url=url,
        fetched_at=fetched_at,
        ttl_days=OEWS_TTL_DAYS,
        license_note=license_note or oews_license_note(),
        byte_count=byte_count,
    )


def _store_ev(
    conn: sqlite3.Connection,
    rows: list[EvZipCount],
    *,
    as_of: str,
    fetched_at: str,
    byte_count: int | None,
    license_note: str | None = None,
    url: str | None = None,
) -> None:
    persist_ev_zip(
        conn,
        rows,
        source_id=CA_EV_DMV_SOURCE_ID,
        url=url or dmv_dataset_url(),
        as_of=as_of,
        fetched_at=fetched_at,
        ttl_days=EV_TTL_DAYS,
        license_note=license_note or ev_license_note(),
        byte_count=byte_count,
    )


def _require_zips(found: tuple[str, ...], *, what: str) -> None:
    if tuple(sorted(found)) != tuple(sorted(DEMO_ZIPS)):
        raise DemoSeedError(f"{what} must contain ZIPs {', '.join(DEMO_ZIPS)}.")


def _read_object(path: Path) -> tuple[dict[str, object], int]:
    if not path.is_file():
        raise DemoSeedError(f"Demo file not found: {path}.")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoSeedError(f"{path.name} is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise DemoSeedError(f"{path.name} must be a JSON object.")
    return payload, len(raw)


def _required_str(value: object, *, what: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise DemoSeedError(f"{what} must be a non-empty string.")
    return value


def _required_int(value: object, *, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DemoSeedError(f"{what} must be an integer.")
    return value


def database_directory(db: Path | None) -> Path:
    """Return the directory ``get_connection`` should open.

    ``None`` is the OS user-data directory. A path ending in ``dce.sqlite``
    uses that file's parent. Any other path is treated as the directory.
    """
    if db is None:
        return user_data_dir()
    if db.suffix == ".sqlite":
        if db.name != DB_FILENAME:
            raise DemoSeedError(f"Database file must be named {DB_FILENAME}.")
        return db.parent
    return db


def _require_stamp(value: str) -> str:
    if re.fullmatch(_FETCHED_AT, value) is None:
        raise DemoSeedError(f"fetched_at must look like 2026-11-09T12:00:00Z, got {value!r}.")
    return value
