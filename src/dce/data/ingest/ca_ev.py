"""California light-duty vehicle counts by ZIP.

Contract
--------
Allowlisted host: ``data.ca.gov``. ``fetch_ev_zip`` reads the California DMV
fuel-type file through the CKAN datastore SQL API and keeps light-duty rows
only. That file is the no-key CEC/DMV path for a single ZIP. The portal names
the current resource "1/1/2026 Vehicle Fuel Type Count by Zip Code"; the row
``Date`` for the San Mateo ZIPs is ``2024-12-31``, and that date is ``as_of``.

Fuel names from that file map as:

* Battery Electric → ``bev``
* Plug-in Hybrid → ``phev``
* Hydrogen Fuel Cell → ``fcev``
* every other light-duty fuel → ``total_ldv`` only

``source`` is ``dmv``. Heavy and unknown duty are excluded from ``total_ldv``.
No API key. This module does not open SQLite. The CEC bulk workbook on
``energy.ca.gov`` is not downloaded here; it has no per-ZIP query API and the
DMV file is the accept path for 94402.

Outside California, a later milestone flags ``ev_proxy=acs_national_fallback``.
Stale after 18 months.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from urllib.parse import quote

from dce.data.ingest.http import IngestError, request_json
from dce.data.registry import TTL_18_MONTHS_DAYS

CA_EV_DMV_SOURCE_ID = "ca_ev_dmv"
EV_TTL_DAYS = TTL_18_MONTHS_DAYS
DMV_RESOURCE_ID = "b459d957-5d94-4b10-999d-770419870364"
DMV_DATASET_URL = "https://data.ca.gov/dataset/vehicle-fuel-type-count-by-zip-code"
_SQL_API = "https://data.ca.gov/api/3/action/datastore_search_sql"
_BEV_FUELS = frozenset({"battery electric"})
_PHEV_FUELS = frozenset({"plug-in hybrid"})
_FCEV_FUELS = frozenset({"hydrogen fuel cell"})
_ALLOWED_SOURCES = frozenset({"cec", "dmv", "fallback"})
_DMV_LICENSE = (
    "California DMV vehicle fuel-type counts by ZIP, published on data.ca.gov. "
    "California open data. Light-duty rows only."
)


@dataclass(frozen=True)
class EvZipCount:
    """Light-duty vehicle counts for one ZIP. ``as_of`` is an ISO date."""

    zip_code: str
    state: str
    bev: float | None
    phev: float | None
    fcev: float | None
    total_ldv: float | None
    as_of: str
    source: str


class EvZipError(IngestError):
    """A California vehicle-count row could not be fetched or parsed."""


def ev_license_note() -> str:
    """Return the ``source_registry`` license note for the DMV file."""
    return _DMV_LICENSE


def dmv_dataset_url() -> str:
    """Return the dataset page stored in ``source_registry`` (no query string)."""
    return DMV_DATASET_URL


def fetch_ev_zip(zip_code: str) -> EvZipCount:
    """Download light-duty fuel counts for one California ZIP from data.ca.gov."""
    code = require_zip(zip_code)
    url = f"{_SQL_API}?sql={quote(dmv_sql(code), safe='')}"
    try:
        payload = request_json(url)
    except IngestError as exc:
        raise EvZipError(f"data.ca.gov vehicle-count request failed for ZIP {code}.") from exc
    return aggregate_ev_records(code, records_from_ckan(payload), source="dmv")


def dmv_sql(zip_code: str) -> str:
    """Return the datastore SQL for one validated ZIP. The ZIP is digits only."""
    code = require_zip(zip_code)
    return (
        'SELECT "Date" AS "Date", "ZIP Code" AS "ZIP Code", "Fuel" AS "Fuel", '
        '"Duty" AS "Duty", SUM("Vehicles") AS "Vehicles" '
        f'FROM "{DMV_RESOURCE_ID}" '
        f"WHERE \"ZIP Code\" = '{code}' AND \"Duty\" = 'Light' "
        'GROUP BY "Date", "ZIP Code", "Fuel", "Duty"'
    )


def records_from_ckan(payload: object) -> list[dict[str, object]]:
    """Return the ``records`` list from a CKAN ``datastore_search_sql`` body."""
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise EvZipError("data.ca.gov did not return a successful datastore result.")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise EvZipError("data.ca.gov datastore result was not an object.")
    records = result.get("records")
    if not isinstance(records, list):
        raise EvZipError("data.ca.gov datastore result has no records list.")
    parsed: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            raise EvZipError("data.ca.gov returned a record that is not an object.")
        parsed.append(record)
    return parsed


def aggregate_ev_records(
    zip_code: str,
    records: Sequence[Mapping[str, object]],
    *,
    source: str,
) -> EvZipCount:
    """Sum light-duty fuel rows into one :class:`EvZipCount`.

    Rows whose duty is not ``Light`` are ignored. Rows for a different ZIP
    raise. Every light-duty fuel counts toward ``total_ldv``.
    """
    code = require_zip(zip_code)
    origin = _require_source(source)
    bev = 0
    phev = 0
    fcev = 0
    total = 0
    as_of: str | None = None
    kept = 0
    for record in records:
        duty = _text(record.get("Duty"), what="Duty")
        if duty.casefold() != "light":
            continue
        row_zip = record.get("ZIP Code")
        if row_zip is not None and _text(row_zip, what="ZIP Code") != code:
            raise EvZipError(f"EV row ZIP {row_zip!r} does not match {code}.")
        row_date = _require_iso_date(_text(record.get("Date"), what="Date"))
        if as_of is None:
            as_of = row_date
        elif as_of != row_date:
            raise EvZipError(f"ZIP {code} has more than one vehicle as_of date.")
        count = _whole_count(record.get("Vehicles"))
        fuel = _text(record.get("Fuel"), what="Fuel").casefold()
        total += count
        if fuel in _BEV_FUELS:
            bev += count
        elif fuel in _PHEV_FUELS:
            phev += count
        elif fuel in _FCEV_FUELS:
            fcev += count
        kept += 1
    if kept == 0 or as_of is None:
        raise EvZipError(f"No light-duty vehicle rows for ZIP {code}.")
    return EvZipCount(
        zip_code=code,
        state="CA",
        bev=float(bev),
        phev=float(phev),
        fcev=float(fcev),
        total_ldv=float(total),
        as_of=as_of,
        source=origin,
    )


def require_zip(zip_code: str) -> str:
    """Return a 5-digit ZIP. Leading zeros are preserved."""
    code = zip_code.strip()
    if len(code) != 5 or not code.isdigit():
        raise EvZipError(f"ZIP must be 5 digits, got {zip_code!r}.")
    return code


def _require_source(source: str) -> str:
    if source not in _ALLOWED_SOURCES:
        raise EvZipError(f"EV source must be cec, dmv, or fallback, got {source!r}.")
    return source


def _text(value: object, *, what: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise EvZipError(f"EV row {what} must be a non-empty string.")
    return value.strip()


def _whole_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise EvZipError(f"Vehicle count must be a whole number, got {value!r}.")
    try:
        number = float(value)
    except ValueError as exc:
        raise EvZipError(f"Vehicle count is not a number: {value!r}.") from exc
    if not number.is_integer() or number < 0:
        raise EvZipError(f"Vehicle count must be a whole number >= 0, got {value!r}.")
    return int(number)


def _require_iso_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EvZipError(f"EV as_of must be an ISO date, got {value!r}.") from exc
    return parsed.isoformat()
