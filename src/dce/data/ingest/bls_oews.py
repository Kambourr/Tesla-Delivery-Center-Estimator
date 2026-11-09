"""BLS OEWS wage fetch.

Contract
--------
Allowlisted host: ``api.bls.gov``. Primary occupation is SOC ``49-3023``
(Automotive Service Technicians and Mechanics), all industries.

Join key (M2): BLS publishes the San Francisco–Oakland metro as CBSA
``41860`` (San Francisco-Oakland-Fremont, CA). The HUD ZIP–CBSA column for
94401–94404 is metropolitan division ``41884``. :func:`oews_area_for_cbsa`
maps that division, and every other July 2023 metropolitan division, to its
parent CBSA. A code that is not a division is unchanged.
``GeoContext.cbsa`` stays the HUD code.

The series id is the 25-character OEWS id documented by BLS:
``OE`` + ``U`` + ``M`` + 7-digit area + 6-digit industry + 6-digit SOC +
2-digit datatype. Annual mean is datatype ``04``. Annual median is ``13``.
May 2025 mean and median for ``41860`` / ``49-3023`` were read from the
public API (no registration key required for this small query).

``as_of`` is 1 May of the survey year. Stale after 18 months. This module
does not open SQLite. ``BLS_API_KEY`` is optional; when it is set the v2
endpoint is used and the key stays in the POST body, not the URL.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from dce.config import api_key as read_api_key
from dce.data.ingest.http import IngestError, request_json
from dce.data.registry import TTL_18_MONTHS_DAYS

BLS_OEWS_SOURCE_ID = "bls_oews"
OEWS_TTL_DAYS = TTL_18_MONTHS_DAYS
OEWS_SOC_AUTO_TECH = "49-3023"
OEWS_SOC_TITLE_AUTO_TECH = "Automotive Service Technicians and Mechanics"
SF_OAKLAND_CBSA = "41860"
SF_OAKLAND_AREA_NAME = "San Francisco-Oakland-Fremont, CA"
OEWS_NATIONAL_AREA = "00000"
OEWS_NATIONAL_AREA_NAME = "United States"
# Delivery-center staffing mix from assumptions.yaml, plus the auto-tech series.
OEWS_DELIVERY_SOCS: tuple[tuple[str, str], ...] = (
    ("41-2031", "Retail Salespersons"),
    ("53-7061", "Cleaners of Vehicles and Equipment"),
    ("53-7062", "Laborers and Freight, Stock, and Material Movers, Hand"),
    ("53-7065", "Stockers and Order Fillers"),
    ("41-1011", "First-Line Supervisors of Retail Sales Workers"),
    (OEWS_SOC_AUTO_TECH, OEWS_SOC_TITLE_AUTO_TECH),
)
# Metropolitan division → parent CBSA. July 2023 OMB delineation (Census list 1).
# OEWS publishes the parent. GeoContext.cbsa stays the division, including 41884.
HUD_DIVISION_TO_OEWS_CBSA = {
    "11244": "31080",
    "11694": "47900",
    "12054": "12060",
    "14454": "14460",
    "15764": "14460",
    "15804": "37980",
    "16984": "16980",
    "19124": "19100",
    "19804": "19820",
    "20994": "16980",
    "21794": "42660",
    "22744": "33100",
    "23104": "19100",
    "23224": "47900",
    "29404": "16980",
    "29414": "16980",
    "29484": "35620",
    "31084": "31080",
    "31924": "12060",
    "33124": "33100",
    "33874": "37980",
    "35004": "35620",
    "35084": "35620",
    "35614": "35620",
    "36084": "41860",
    "37964": "37980",
    "40484": "14460",
    "41304": "45300",
    "41884": "41860",
    "42034": "41860",
    "42644": "42660",
    "45104": "42660",
    "45294": "45300",
    "47664": "19820",
    "47764": "47900",
    "48424": "33100",
    "48864": "37980",
}
_BLS_V1_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
_BLS_V2_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
_INDUSTRY_ALL = "000000"
_DATATYPE_ANNUAL_MEAN = "04"
_DATATYPE_ANNUAL_MEDIAN = "13"
_OEWS_LICENSE = (
    "U.S. Bureau of Labor Statistics Occupational Employment and Wage Statistics. "
    "Public domain (US government work)."
)


@dataclass(frozen=True)
class OewsWage:
    """Metro occupation wage. Annual dollars. ``as_of`` is an ISO date."""

    area_code: str
    area_name: str
    soc: str
    soc_title: str
    mean_annual: float | None
    median_annual: float | None
    as_of: str


class OewsError(IngestError):
    """A BLS OEWS series could not be fetched or parsed."""


def oews_license_note() -> str:
    """Return the ``source_registry`` license note for OEWS."""
    return _OEWS_LICENSE


def oews_dataset_url() -> str:
    """Return the BLS timeseries URL stored in ``source_registry`` (no API key)."""
    return _BLS_V2_URL


def oews_area_for_cbsa(cbsa: str) -> str:
    """Return the BLS OEWS area for a HUD CBSA or metropolitan-division code.

    Division ``41884`` (San Francisco–San Mateo–Redwood City) becomes parent
    CBSA ``41860``. The same table maps the other July 2023 metropolitan
    divisions. A code that is not in the table is returned unchanged.
    """
    code = normalize_cbsa(cbsa)
    return HUD_DIVISION_TO_OEWS_CBSA.get(code, code)


def normalize_cbsa(area_code: str) -> str:
    """Return a 5-digit CBSA. A 7-digit code is accepted when it is zero-padded."""
    digits = area_code.strip()
    if len(digits) == 7 and digits.startswith("00") and digits.isdigit():
        digits = digits[2:]
    if len(digits) != 5 or not digits.isdigit():
        raise OewsError(
            "OEWS area_code must be a 5-digit CBSA (or that code padded to 7 digits), "
            f"got {area_code!r}."
        )
    return digits


def normalize_soc(soc: str) -> str:
    """Return SOC text as ``NN-NNNN``. ``493023`` and ``49-3023`` both work."""
    text = soc.strip()
    if len(text) == 7 and text[2] == "-" and text[:2].isdigit() and text[3:].isdigit():
        return text
    if len(text) == 6 and text.isdigit():
        return f"{text[:2]}-{text[2:]}"
    raise OewsError(f"SOC must look like 49-3023, got {soc!r}.")


def oews_national_series_id(soc: str, datatype: str) -> str:
    """Build the 25-character national OEWS series id (area type ``N``)."""
    if len(datatype) != 2 or not datatype.isdigit():
        raise OewsError(f"OEWS datatype must be 2 digits, got {datatype!r}.")
    occupation = normalize_soc(soc).replace("-", "")
    return f"OEUN0000000{_INDUSTRY_ALL}{occupation}{datatype}"


def oews_series_id(area_code: str, soc: str, datatype: str) -> str:
    """Build one 25-character OEWS series id for a metro, all industries."""
    if len(datatype) != 2 or not datatype.isdigit():
        raise OewsError(f"OEWS datatype must be 2 digits, got {datatype!r}.")
    area = normalize_cbsa(area_code)
    occupation = normalize_soc(soc).replace("-", "")
    return f"OEUM00{area}{_INDUSTRY_ALL}{occupation}{datatype}"


def oews_as_of(year: int) -> str:
    """Return 1 May of the OEWS survey year."""
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise OewsError(f"OEWS year must be an integer from 2000 through 2100, got {year!r}.")
    return f"{year}-05-01"


def fetch_oews_wage(
    area_code: str,
    soc: str,
    *,
    area_name: str | None = None,
    soc_title: str | None = None,
    end_year: int | None = None,
) -> OewsWage:
    """Download one metro × SOC annual mean and median wage.

    ``area_code`` may be the HUD division. The stored code is the OEWS CBSA
    from :func:`oews_area_for_cbsa`. ``end_year`` defaults to the current UTC
    year. The latest survey year present in both series is kept.
    """
    area = oews_area_for_cbsa(area_code)
    occupation = normalize_soc(soc)
    title = _soc_title(occupation, soc_title)
    name = _area_name(area, area_name)
    mean_id = oews_series_id(area, occupation, _DATATYPE_ANNUAL_MEAN)
    median_id = oews_series_id(area, occupation, _DATATYPE_ANNUAL_MEDIAN)
    vintage = _end_year(end_year)
    payload = _post_series((mean_id, median_id), start_year=vintage - 2, end_year=vintage)
    return parse_oews_payload(
        payload,
        area_code=area,
        area_name=name,
        soc=occupation,
        soc_title=title,
        mean_series_id=mean_id,
        median_series_id=median_id,
    )


def fetch_oews_area_wages(
    areas: Sequence[tuple[str, str]],
    socs: Sequence[tuple[str, str]],
    *,
    datatypes: Sequence[str] = (_DATATYPE_ANNUAL_MEAN, _DATATYPE_ANNUAL_MEDIAN),
    national: bool = False,
    end_year: int | None = None,
) -> tuple[OewsWage, ...]:
    """Download wages for several areas and occupations in one BLS request.

    ``areas`` is ``(area_code, area_name)``. ``socs`` is ``(soc, title)``.
    The caller keeps ``len(areas) * len(socs) * len(datatypes)`` at or below
    25, which is the unregistered BLS limit for one query. A series with no
    annual observation is skipped. ``national=True`` ignores ``areas`` and
    stores :data:`OEWS_NATIONAL_AREA`.
    """
    if not socs:
        raise OewsError("OEWS fetch needs at least one SOC.")
    if not national and not areas:
        raise OewsError("OEWS fetch needs at least one area.")
    vintage = _end_year(end_year)
    specs = _series_specs(areas, socs, datatypes, national=national)
    if len(specs) > 25:
        raise OewsError(f"OEWS fetch asked for {len(specs)} series. One request can carry 25.")
    payload = _post_series(
        tuple(spec[0] for spec in specs), start_year=vintage - 1, end_year=vintage
    )
    points = _optional_annual_points(payload)
    return _wages_from_points(specs, points, vintage)


def parse_oews_bulk_csv(
    text: str,
    *,
    year: int,
    socs: frozenset[str] | None = None,
) -> tuple[OewsWage, ...]:
    """Parse a BLS OEWS all-data CSV (metro or national).

    Required headers, matched without case: ``AREA``, ``AREA_TITLE``,
    ``OCC_CODE``, ``A_MEAN``, ``A_MEDIAN``. When ``NAICS`` is present, only
    cross-industry ``000000`` rows are kept. When ``O_GROUP`` is present, only
    ``detailed`` rows are kept. ``*`` and ``#`` wages are missing. A 7-digit
    area that starts with ``00`` is stored as the 5-digit CBSA. ``0000000``
    is the national area.
    """
    as_of = oews_as_of(year)
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        raise OewsError("OEWS bulk file has no data rows.")
    header = [cell.strip().upper() for cell in rows[0]]
    index = {name: position for position, name in enumerate(header)}
    for name in ("AREA", "AREA_TITLE", "OCC_CODE", "A_MEAN", "A_MEDIAN"):
        if name not in index:
            raise OewsError(f"OEWS bulk file is missing the {name} column.")
    wanted = None if socs is None else {normalize_soc(soc) for soc in socs}
    found: dict[tuple[str, str], OewsWage] = {}
    for cells in rows[1:]:
        if not any(cell.strip() for cell in cells):
            continue
        if "NAICS" in index and _cell(cells, index["NAICS"]) not in {"", "000000"}:
            continue
        if "O_GROUP" in index and _cell(cells, index["O_GROUP"]).casefold() not in {
            "",
            "detailed",
        }:
            continue
        soc = normalize_soc(_cell(cells, index["OCC_CODE"]))
        if wanted is not None and soc not in wanted:
            continue
        title = _cell(cells, index["OCC_TITLE"]) if "OCC_TITLE" in index else ""
        if title == "":
            title = _soc_title(soc, None) if soc == OEWS_SOC_AUTO_TECH else soc
        area = _bulk_area(_cell(cells, index["AREA"]))
        key = (area, soc)
        found[key] = OewsWage(
            area_code=area,
            area_name=_cell(cells, index["AREA_TITLE"]) or area,
            soc=soc,
            soc_title=title,
            mean_annual=_bulk_wage(_cell(cells, index["A_MEAN"])),
            median_annual=_bulk_wage(_cell(cells, index["A_MEDIAN"])),
            as_of=as_of,
        )
    if not found:
        raise OewsError("OEWS bulk file has no rows for the requested occupations.")
    return tuple(found[key] for key in sorted(found))


def parse_oews_payload(
    payload: object,
    *,
    area_code: str,
    area_name: str,
    soc: str,
    soc_title: str,
    mean_series_id: str,
    median_series_id: str,
) -> OewsWage:
    """Parse a BLS timeseries JSON object into one wage row."""
    if not isinstance(payload, dict):
        raise OewsError("BLS response was not a JSON object.")
    status = payload.get("status")
    if status != "REQUEST_SUCCEEDED":
        raise OewsError(f"BLS request failed ({status}): {_messages(payload)}.")
    results = payload.get("Results")
    if not isinstance(results, dict):
        raise OewsError("BLS response has no Results object.")
    series = results.get("series")
    if not isinstance(series, list):
        raise OewsError("BLS response has no series list.")
    points = {
        mean_series_id: _annual_points(series, mean_series_id),
        median_series_id: _annual_points(series, median_series_id),
    }
    common = sorted(set(points[mean_series_id]) & set(points[median_series_id]))
    if not common:
        raise OewsError(
            "BLS response has no survey year with both the annual mean and median series."
        )
    year = common[-1]
    return OewsWage(
        area_code=normalize_cbsa(area_code),
        area_name=_require_text(area_name, what="area_name"),
        soc=normalize_soc(soc),
        soc_title=_require_text(soc_title, what="soc_title"),
        mean_annual=points[mean_series_id][year],
        median_annual=points[median_series_id][year],
        as_of=oews_as_of(year),
    )


def _series_specs(
    areas: Sequence[tuple[str, str]],
    socs: Sequence[tuple[str, str]],
    datatypes: Sequence[str],
    *,
    national: bool,
) -> list[tuple[str, str, str, str, str]]:
    """Return ``(series_id, area, area_name, soc, title)`` for each mean or median."""
    specs: list[tuple[str, str, str, str, str]] = []
    targets = ((OEWS_NATIONAL_AREA, OEWS_NATIONAL_AREA_NAME),) if national else areas
    for area_code, area_name in targets:
        for soc, title in socs:
            for datatype in datatypes:
                if datatype not in {_DATATYPE_ANNUAL_MEAN, _DATATYPE_ANNUAL_MEDIAN}:
                    raise OewsError(f"OEWS datatype must be 04 or 13, got {datatype!r}.")
                series_id = (
                    oews_national_series_id(soc, datatype)
                    if national or area_code == OEWS_NATIONAL_AREA
                    else oews_series_id(area_code, soc, datatype)
                )
                stored = OEWS_NATIONAL_AREA if national else oews_area_for_cbsa(area_code)
                specs.append((series_id, stored, area_name, normalize_soc(soc), title))
    return specs


def _optional_annual_points(payload: object) -> dict[str, dict[int, float | None]]:
    if not isinstance(payload, dict):
        raise OewsError("BLS response was not a JSON object.")
    status = payload.get("status")
    if status != "REQUEST_SUCCEEDED":
        raise OewsError(f"BLS request failed ({status}): {_messages(payload)}.")
    results = payload.get("Results")
    if not isinstance(results, dict):
        raise OewsError("BLS response has no Results object.")
    series = results.get("series")
    if not isinstance(series, list):
        raise OewsError("BLS response has no series list.")
    points: dict[str, dict[int, float | None]] = {}
    for item in series:
        if not isinstance(item, dict):
            raise OewsError("BLS series entry is not an object.")
        series_id = item.get("seriesID")
        data = item.get("data")
        if not isinstance(series_id, str) or not isinstance(data, list) or not data:
            continue
        annual: dict[int, float | None] = {}
        for point in data:
            if not isinstance(point, dict) or point.get("period") != "A01":
                continue
            year_text = point.get("year")
            if not isinstance(year_text, str) or not year_text.isdigit():
                continue
            annual[int(year_text)] = _wage(point.get("value"), series_id=series_id)
        if annual:
            points[series_id] = annual
    return points


def _wages_from_points(
    specs: Sequence[tuple[str, str, str, str, str]],
    points: dict[str, dict[int, float | None]],
    vintage: int,
) -> tuple[OewsWage, ...]:
    grouped: dict[tuple[str, str], dict[str, dict[int, float | None]]] = {}
    names: dict[tuple[str, str], tuple[str, str]] = {}
    for series_id, area, area_name, soc, title in specs:
        key = (area, soc)
        grouped.setdefault(key, {})[series_id] = points.get(series_id, {})
        names[key] = (area_name, title)
    rows: list[OewsWage] = []
    for area, soc in sorted(grouped):
        series_map = grouped[(area, soc)]
        mean_id = next(
            (series_id for series_id in series_map if series_id.endswith(_DATATYPE_ANNUAL_MEAN)),
            None,
        )
        median_id = next(
            (series_id for series_id in series_map if series_id.endswith(_DATATYPE_ANNUAL_MEDIAN)),
            None,
        )
        mean_points = series_map.get(mean_id, {}) if mean_id else {}
        median_points = series_map.get(median_id, {}) if median_id else {}
        years = sorted(set(mean_points) | set(median_points))
        years = [year for year in years if year <= vintage]
        if not years:
            continue
        year = years[-1]
        area_name, title = names[(area, soc)]
        rows.append(
            OewsWage(
                area_code=area,
                area_name=_require_text(area_name, what="area_name"),
                soc=soc,
                soc_title=_require_text(title, what="soc_title"),
                mean_annual=mean_points.get(year),
                median_annual=median_points.get(year),
                as_of=oews_as_of(year),
            )
        )
    return tuple(rows)


def _cell(cells: Sequence[str], index: int) -> str:
    if index >= len(cells):
        return ""
    return cells[index].strip()


def _bulk_area(value: str) -> str:
    text = value.strip()
    if text in {"0000000", "00000"}:
        return OEWS_NATIONAL_AREA
    if len(text) == 7 and text.startswith("00") and text.isdigit():
        return text[2:]
    if len(text) == 5 and text.isdigit():
        return text
    raise OewsError(f"OEWS AREA must be a CBSA or 0000000, got {value!r}.")


def _bulk_wage(value: str) -> float | None:
    text = value.strip().replace(",", "")
    if text in {"", "*", "#", "**", "-", "NA"}:
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise OewsError(f"OEWS wage is not a number: {value!r}.") from exc
    if number < 0:
        raise OewsError(f"OEWS wage is negative: {number}.")
    return number


def _post_series(series_ids: Sequence[str], *, start_year: int, end_year: int) -> object:
    body: dict[str, object] = {
        "seriesid": list(series_ids),
        "startyear": str(start_year),
        "endyear": str(end_year),
    }
    key = read_api_key("BLS_API_KEY")
    url = _BLS_V1_URL
    if key is not None:
        body["registrationkey"] = key
        url = _BLS_V2_URL
    encoded = _json_bytes(body)
    try:
        return request_json(
            url,
            method="POST",
            body=encoded,
            headers={"Content-Type": "application/json"},
        )
    except IngestError as exc:
        raise OewsError("BLS OEWS request failed. The API key is not included here.") from exc


def _json_bytes(body: dict[str, object]) -> bytes:
    return json.dumps(body).encode("utf-8")


def _annual_points(series: list[object], series_id: str) -> dict[int, float | None]:
    match: dict[str, object] | None = None
    for item in series:
        if isinstance(item, dict) and item.get("seriesID") == series_id:
            match = item
            break
    if match is None:
        raise OewsError(f"BLS response did not include series {series_id}.")
    data = match.get("data")
    if not isinstance(data, list) or not data:
        raise OewsError(f"BLS series {series_id} has no data points.")
    points: dict[int, float | None] = {}
    for point in data:
        if not isinstance(point, dict):
            raise OewsError(f"BLS series {series_id} has a data point that is not an object.")
        if point.get("period") != "A01":
            continue
        year_text = point.get("year")
        if not isinstance(year_text, str) or not year_text.isdigit():
            raise OewsError(f"BLS series {series_id} has no survey year.")
        points[int(year_text)] = _wage(point.get("value"), series_id=series_id)
    if not points:
        raise OewsError(f"BLS series {series_id} has no annual (A01) observations.")
    return points


def _wage(value: object, *, series_id: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise OewsError(f"BLS series {series_id} wage was not a string.")
    text = value.strip()
    if text == "" or text == "-":
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise OewsError(f"BLS series {series_id} wage is not a number: {value!r}.") from exc
    if number < 0:
        raise OewsError(f"BLS series {series_id} wage is negative: {number}.")
    return number


def _messages(payload: dict[str, object]) -> str:
    raw = payload.get("message")
    if isinstance(raw, list):
        texts = [str(item) for item in raw if str(item).strip()]
        if texts:
            return "; ".join(texts)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "no message"


def _soc_title(soc: str, explicit: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    if soc == OEWS_SOC_AUTO_TECH:
        return OEWS_SOC_TITLE_AUTO_TECH
    raise OewsError(
        f"No SOC title is recorded for {soc}. Pass soc_title= for occupations other than 49-3023."
    )


def _area_name(area_code: str, explicit: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    if area_code == SF_OAKLAND_CBSA:
        return SF_OAKLAND_AREA_NAME
    raise OewsError(
        f"No BLS area title is recorded for CBSA {area_code}. "
        "Pass area_name= once the OEWS title is confirmed."
    )


def _require_text(value: str, *, what: str) -> str:
    text = value.strip()
    if text == "":
        raise OewsError(f"{what} must not be blank.")
    return text


def _end_year(end_year: int | None) -> int:
    if end_year is None:
        return datetime.now(UTC).year
    if isinstance(end_year, bool) or not isinstance(end_year, int):
        raise OewsError(f"end_year must be an integer, got {end_year!r}.")
    return end_year
