"""BLS OEWS wage fetch.

Contract
--------
Allowlisted host: ``api.bls.gov``. Primary occupation is SOC ``49-3023``
(Automotive Service Technicians and Mechanics), all industries.

Join key (M2): BLS publishes the San Francisco–Oakland metro as CBSA
``41860`` (San Francisco-Oakland-Fremont, CA). The HUD ZIP–CBSA column for
94401–94404 is metropolitan division ``41884``. :func:`oews_area_for_cbsa`
maps that division to ``41860`` and leaves every other CBSA unchanged.
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

import json
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
# HUD metropolitan division → the parent CBSA BLS uses for OEWS.
HUD_DIVISION_TO_OEWS_CBSA = {"41884": SF_OAKLAND_CBSA}
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
    CBSA ``41860``. Any other 5-digit code is returned unchanged.
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


def _post_series(series_ids: tuple[str, str], *, start_year: int, end_year: int) -> object:
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
