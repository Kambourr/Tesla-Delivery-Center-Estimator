"""Census ACS 5-year fetch for one ZCTA.

Contract
--------
Allowlisted host: ``api.census.gov``. One call reads the detailed tables and
one reads the subject table. Variables:

* ``B01003_001E`` population
* ``B11001_001E`` households (total). The non-California demand fallback
  weights ZIPs by this count.
* ``B19013_001E`` median household income
* ``B25046_001E`` aggregate vehicles available
* ``B25064_001E`` median gross rent (dollars per month). The rent resolver
  uses this as the local adjuster and as the low-confidence residential proxy.
* ``B25077_001E`` median home value (the rent model reads this later;
  ``2000001`` is the Census top-code for $2,000,000+)
* ``S0801_C01_046E`` mean travel time to work, in minutes

``fetch_zcta_acs`` needs ``CENSUS_API_KEY`` (environment or a local ``.env``).
The key is a query parameter on the request and is never written to
``source_registry``. The San Mateo demo loads ``data/demo/san_mateo`` and does
not need the key. This module does not open SQLite. Persistence is
:mod:`dce.data.persist`.

Refresh annually. ``as_of`` is ``{year}-12-31``, the end of the ACS reference
year. Stale after :data:`dce.data.registry.TTL_18_MONTHS_DAYS`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dce.config import api_key as read_api_key
from dce.data.ingest.http import IngestError, encode_query, request_json
from dce.data.registry import TTL_18_MONTHS_DAYS

CENSUS_ACS_SOURCE_ID = "census_acs"
ACS_TTL_DAYS = TTL_18_MONTHS_DAYS
ACS_DEMO_YEAR = 2024
POPULATION_VARIABLE = "B01003_001E"
HOUSEHOLDS_VARIABLE = "B11001_001E"
INCOME_VARIABLE = "B19013_001E"
VEHICLES_VARIABLE = "B25046_001E"
HOME_VALUE_VARIABLE = "B25077_001E"
GROSS_RENT_VARIABLE = "B25064_001E"
COMMUTE_VARIABLE = "S0801_C01_046E"
_ZCTA_COLUMN = "zip code tabulation area"
_DETAILED_VARIABLES = (
    "NAME",
    POPULATION_VARIABLE,
    HOUSEHOLDS_VARIABLE,
    INCOME_VARIABLE,
    VEHICLES_VARIABLE,
    HOME_VALUE_VARIABLE,
    GROSS_RENT_VARIABLE,
)
_COMMUTE_VARIABLES = ("NAME", COMMUTE_VARIABLE)
_SENTINELS = frozenset(
    {
        -111111111.0,
        -222222222.0,
        -333333333.0,
        -555555555.0,
        -666666666.0,
        -888888888.0,
        -999999999.0,
    }
)
_CENSUS_LICENSE = (
    "U.S. Census Bureau American Community Survey 5-year estimates. "
    "Public domain (US government work)."
)


@dataclass(frozen=True)
class ZctaAcs:
    """ACS facts for one ZCTA. Counts and dollars are ``None`` when suppressed."""

    zcta: str
    year: int
    population: float | None
    median_hh_income: float | None
    vehicles_available: float | None
    mean_commute: float | None
    median_home_value: float | None
    households: float | None = None
    median_gross_rent: float | None = None


class CensusAcsError(IngestError):
    """The Census ACS response could not be turned into a ZCTA row."""


class CensusApiKeyError(CensusAcsError):
    """``CENSUS_API_KEY`` is required for a live ACS fetch and was not set."""


def census_license_note() -> str:
    """Return the ``source_registry`` license note for ACS."""
    return _CENSUS_LICENSE


def census_dataset_url(year: int) -> str:
    """Return the detailed-table dataset URL with no API key in it."""
    return f"https://api.census.gov/data/{_require_year(year)}/acs/acs5"


def acs_as_of(year: int) -> str:
    """Return the ISO ``as_of`` for an ACS 5-year vintage (31 December of ``year``)."""
    return f"{_require_year(year)}-12-31"


def fetch_zcta_acs(zcta: str, *, year: int, api_key: str | None = None) -> ZctaAcs:
    """Download ACS 5-year fields for one ZCTA from ``api.census.gov``.

    ``api_key`` overrides the environment. A missing key raises
    :class:`CensusApiKeyError` before any socket is opened.
    """
    code = require_zcta(zcta)
    vintage = _require_year(year)
    key = _resolve_key(api_key)
    detailed = _fetch_variables(
        census_dataset_url(vintage),
        _DETAILED_VARIABLES,
        zcta=code,
        census_key=key,
    )
    subject = _fetch_variables(
        f"{census_dataset_url(vintage)}/subject",
        _COMMUTE_VARIABLES,
        zcta=code,
        census_key=key,
    )
    return zcta_acs_from_variables(code, vintage, {**detailed, **subject})


def parse_census_table(table: object, *, year: int) -> list[ZctaAcs]:
    """Parse an ``api.census.gov`` ``get=`` table (header row, then data rows)."""
    vintage = _require_year(year)
    rows = variables_from_census_table(table)
    return [zcta_acs_from_variables(_zcta_from_row(row), vintage, row) for row in rows]


def variables_from_census_table(table: object) -> list[dict[str, str | None]]:
    """Return one variable dictionary per data row of a Census table."""
    if isinstance(table, dict):
        message = table.get("error") or table.get("message") or "Census returned an error object."
        raise CensusAcsError(str(message))
    if not isinstance(table, list) or len(table) < 2:
        raise CensusAcsError("Census ACS table needs a header row and at least one data row.")
    header = _string_row(table[0], what="header")
    parsed: list[dict[str, str | None]] = []
    for raw in table[1:]:
        cells = _data_row(raw, width=len(header))
        parsed.append(dict(zip(header, cells, strict=True)))
    return parsed


def zcta_acs_from_variables(zcta: str, year: int, values: Mapping[str, str | None]) -> ZctaAcs:
    """Build one :class:`ZctaAcs` from Census variable names."""
    return ZctaAcs(
        zcta=require_zcta(zcta),
        year=_require_year(year),
        population=_estimate(values.get(POPULATION_VARIABLE)),
        median_hh_income=_estimate(values.get(INCOME_VARIABLE)),
        vehicles_available=_estimate(values.get(VEHICLES_VARIABLE)),
        mean_commute=_estimate(values.get(COMMUTE_VARIABLE)),
        median_home_value=_estimate(values.get(HOME_VALUE_VARIABLE)),
        households=_estimate(values.get(HOUSEHOLDS_VARIABLE)),
        median_gross_rent=_estimate(values.get(GROSS_RENT_VARIABLE)),
    )


def zcta_acs_from_summary_files(
    year: int,
    tables: Mapping[str, str],
) -> tuple[ZctaAcs, ...]:
    """Build ZCTA rows from ACS 5-year table-based summary files.

    ``tables`` maps an API variable name (``B01003_001E``) to the text of
    ``acsdt5y{year}-b01003.dat``. The summary file names the same estimate
    ``B01003_E001``. Only ZCTA rows (``GEO_ID`` prefix ``860Z200US``) are kept.
    A variable that is absent leaves that field ``None``.
    """
    vintage = _require_year(year)
    parsed = {name: _zcta_column(text, name) for name, text in tables.items()}
    codes = sorted({zcta for column in parsed.values() for zcta in column})
    if not codes:
        raise CensusAcsError("ACS summary files have no ZCTA rows.")
    rows: list[ZctaAcs] = []
    for zcta in codes:
        values = {name: column.get(zcta) for name, column in parsed.items()}
        rows.append(zcta_acs_from_variables(zcta, vintage, values))
    return tuple(rows)


def require_zcta(zcta: str) -> str:
    """Return a 5-digit ZCTA. Leading zeros are preserved."""
    code = zcta.strip()
    if len(code) != 5 or not code.isdigit():
        raise CensusAcsError(f"ZCTA must be 5 digits, got {zcta!r}.")
    return code


def _fetch_variables(
    dataset_url: str,
    variables: tuple[str, ...],
    *,
    zcta: str,
    census_key: str,
) -> dict[str, str | None]:
    query = encode_query(
        {
            "get": ",".join(variables),
            "for": f"zip code tabulation area:{zcta}",
            "key": census_key,
        }
    )
    url = f"{dataset_url}?{query}"
    try:
        payload = request_json(url)
    except IngestError as exc:
        raise CensusAcsError(
            "Census ACS request failed. Check CENSUS_API_KEY. The key is not included here."
        ) from exc
    rows = variables_from_census_table(payload)
    if len(rows) != 1:
        raise CensusAcsError(f"Census returned {len(rows)} rows for ZCTA {zcta}; expected 1.")
    got = _zcta_from_row(rows[0])
    if got != zcta:
        raise CensusAcsError(f"Census returned ZCTA {got} for a request of {zcta}.")
    return rows[0]


def _resolve_key(explicit: str | None) -> str:
    if explicit is not None and explicit.strip() != "":
        return explicit.strip()
    found = read_api_key("CENSUS_API_KEY")
    if found is None:
        raise CensusApiKeyError(
            "Census ACS fetch needs CENSUS_API_KEY in the environment or a local .env file. "
            "The San Mateo demo seed loads data/demo/san_mateo and does not need the key."
        )
    return found


def _require_year(year: int) -> int:
    if isinstance(year, bool) or not isinstance(year, int) or not 2009 <= year <= 2100:
        raise CensusAcsError(f"ACS year must be an integer from 2009 through 2100, got {year!r}.")
    return year


def _zcta_from_row(row: Mapping[str, str | None]) -> str:
    raw = row.get(_ZCTA_COLUMN)
    if raw is None or raw.strip() == "":
        raise CensusAcsError("Census ACS row has no ZCTA column.")
    return require_zcta(raw)


def _string_row(value: object, *, what: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(cell, str) for cell in value):
        raise CensusAcsError(f"Census ACS {what} must be a non-empty list of strings.")
    return [str(cell) for cell in value]


def _data_row(value: object, *, width: int) -> list[str | None]:
    if not isinstance(value, list) or len(value) != width:
        raise CensusAcsError("Census ACS row width does not match the header.")
    cells: list[str | None] = []
    for cell in value:
        if cell is None:
            cells.append(None)
        elif isinstance(cell, str):
            cells.append(cell)
        elif isinstance(cell, bool) or not isinstance(cell, (int, float)):
            raise CensusAcsError("Census ACS cell is not a string or number.")
        else:
            cells.append(str(cell))
    return cells


def _zcta_column(text: str, variable: str) -> dict[str, str | None]:
    """Return ZCTA -> estimate text for one summary file."""
    summary_name = _summary_estimate_name(variable)
    lines = text.splitlines()
    if not lines:
        raise CensusAcsError(f"ACS summary file for {variable} is empty.")
    header = lines[0].split("|")
    try:
        column = header.index(summary_name)
    except ValueError as exc:
        raise CensusAcsError(
            f"ACS summary file for {variable} has no {summary_name} column."
        ) from exc
    found: dict[str, str | None] = {}
    for line in lines[1:]:
        if not line.startswith("860Z200US"):
            continue
        cells = line.split("|")
        if len(cells) <= column:
            raise CensusAcsError(f"ACS summary row for {variable} is shorter than the header.")
        geo = cells[0]
        if len(geo) < 5 or not geo[-5:].isdigit():
            continue
        zcta = geo[-5:]
        cell = cells[column].strip()
        found[zcta] = None if cell == "" else cell
    return found


def _summary_estimate_name(variable: str) -> str:
    """Map ``B01003_001E`` to the summary-file name ``B01003_E001``."""
    table, _, line = variable.partition("_")
    if len(line) != 4 or not line[:-1].isdigit() or not line.endswith("E"):
        raise CensusAcsError(f"ACS variable must look like B01003_001E, got {variable!r}.")
    return f"{table}_E{line[:-1]}"


def _estimate(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if text == "" or text == "-" or text.lower() == "null":
        return None
    try:
        number = float(text)
    except ValueError as exc:
        raise CensusAcsError(f"Census estimate is not a number: {value!r}.") from exc
    if number in _SENTINELS:
        return None
    return number
