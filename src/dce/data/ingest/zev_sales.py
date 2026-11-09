"""California Energy Commission new ZEV sales, and the non-California fallback.

Contract
--------
Allowlisted host: ``energy.ca.gov``. ``fetch_zev_sales`` reads the file index
at ``/files/zev-and-infrastructure-stats-data``, follows the
``New_ZEV_Sales_*.xlsx`` link on that host, and parses the workbook.

The ZIP sheet has no make. It is ``Data_Year``, ``Quarter``, ``ZIP``,
``FUEL_TYPE`` (``Electric``, ``PHEV``, ``Hydrogen``), and
``Number of Vehicles``. ``Electric`` is the battery-electric count. The
County sheet adds ``MAKE`` and ``MODEL``. Tesla deliveries for a California
ZIP are that ZIP's Electric sales times Tesla's share of Electric sales in
the county or in a named region (the 9-county Bay Area share is the San
Mateo research ratio). Use a calendar year, or the trailing quarters ending
at the newest quarter in the file. ``as_of`` is the last day of that newest
quarter (the 2026-10-13 file ends at 2026 Q3, so ``as_of`` is 2026-09-30).

Outside California the workbook has no rows. ``allocate_state_tesla_volume``
splits a state Tesla total across ZIPs by
``households * (income / income_ref) ** 0.3 * (ev_share / ev_ref) ** 0.5``.
Those exponents and the default references (income 80,000, EV share 0.03)
are the existing demand-factor elasticities. A ZIP with no households,
income, or EV counts is left out. This module does not open SQLite.
"""

from __future__ import annotations

import io
import math
import re
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

from dce.data.ingest.http import IngestError, request_bytes
from dce.data.registry import TTL_18_MONTHS_DAYS

ZEV_SALES_SOURCE_ID = "cec_zev_sales"
ZEV_TTL_DAYS = TTL_18_MONTHS_DAYS
ZEV_CATALOG_URL = "https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data"
ZEV_WORKBOOK_MAX_BYTES = 16_777_216
BAY_AREA_COUNTIES = (
    "Alameda",
    "Contra Costa",
    "Marin",
    "Napa",
    "San Francisco",
    "San Mateo",
    "Santa Clara",
    "Solano",
    "Sonoma",
)
INCOME_REFERENCE = 80_000.0
EV_SHARE_REFERENCE = 0.03
INCOME_ELASTICITY = 0.3
EV_SHARE_ELASTICITY = 0.5
_BEV_FUEL = "electric"
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}
_FILE_DATE = re.compile(r"Last_updated_(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_LICENSE = (
    "California Energy Commission New ZEV Sales workbook. California open data. "
    "ZIP rows are fuel counts. Tesla make is on the county sheet."
)


class ZevSalesError(IngestError):
    """CEC sales could not be fetched or parsed, or a fallback input is unusable."""


@dataclass(frozen=True)
class ZevZipSales:
    """New ZEV sales for one California ZIP, one quarter, and one fuel. No make."""

    zip_code: str
    state: str
    data_year: int
    quarter: int
    fuel_type: str
    vehicles: int
    as_of: str
    source: str


@dataclass(frozen=True)
class ZevCountySales:
    """New ZEV sales for one county, quarter, fuel, and make. Models are summed."""

    county: str
    state: str
    data_year: int
    quarter: int
    fuel_type: str
    make: str
    vehicles: int
    as_of: str
    source: str


@dataclass(frozen=True)
class ZevSalesBatch:
    """One parsed CEC workbook. ``as_of`` is the end of the newest quarter."""

    as_of: str
    zip_sales: tuple[ZevZipSales, ...]
    county_sales: tuple[ZevCountySales, ...]
    source_url: str
    byte_count: int


@dataclass(frozen=True)
class ZipDemandProfile:
    """Per-ZIP inputs for the non-California allocation.

    ``None`` on households, income, EV stock, or light-duty total means the
    ZIP has no data and receives none of the state volume.
    """

    zip_code: str
    households: float | None
    median_hh_income: float | None
    ev_stock: float | None
    total_ldv: float | None


def zev_license_note() -> str:
    """Return the ``source_registry`` license note for the CEC workbook."""
    return _LICENSE


def zev_catalog_url() -> str:
    """Return the CEC file index stored in ``source_registry``."""
    return ZEV_CATALOG_URL


def fetch_zev_sales() -> ZevSalesBatch:
    """Download the current New ZEV Sales workbook from ``energy.ca.gov``."""
    try:
        catalog = request_bytes(ZEV_CATALOG_URL, timeout=60)
    except IngestError as exc:
        raise ZevSalesError("energy.ca.gov ZEV file index could not be downloaded.") from exc
    download = newest_zev_workbook_url(catalog.decode("utf-8", errors="replace"))
    try:
        payload = request_bytes(download, timeout=120, max_bytes=ZEV_WORKBOOK_MAX_BYTES)
    except IngestError as exc:
        raise ZevSalesError(
            "energy.ca.gov New ZEV Sales workbook could not be downloaded."
        ) from exc
    return parse_zev_workbook(payload, source_url=download)


def newest_zev_workbook_url(catalog_html: str) -> str:
    """Return the absolute URL of the newest ``New_ZEV_Sales`` ``.xlsx`` link."""
    matches: list[tuple[date, str]] = []
    for href, label in _anchor_texts(catalog_html):
        name = label.strip()
        if not name.lower().startswith("new_zev_sales") or not name.lower().endswith(".xlsx"):
            continue
        found = _FILE_DATE.search(name)
        if found is None:
            continue
        month, day, year = (int(part) for part in found.groups())
        try:
            published = date(year, month, day)
        except ValueError as exc:
            raise ZevSalesError(f"ZEV workbook date is not a real date: {name}.") from exc
        absolute = urljoin(ZEV_CATALOG_URL, href)
        parts = urlsplit(absolute)
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
        matches.append((published, cleaned))
    if not matches:
        raise ZevSalesError("The CEC file index has no New_ZEV_Sales workbook link.")
    matches.sort()
    return matches[-1][1]


def parse_zev_workbook(payload: bytes, *, source_url: str) -> ZevSalesBatch:
    """Parse the ZIP and County sheets of a CEC New ZEV Sales workbook."""
    sheets = _sheet_rows(payload)
    try:
        zip_rows = sheets["ZIP"]
        county_rows = sheets["County"]
    except KeyError as exc:
        raise ZevSalesError("ZEV workbook must contain ZIP and County sheets.") from exc
    zip_totals = _accumulate_zip(zip_rows)
    county_totals = _accumulate_county(county_rows)
    if not zip_totals or not county_totals:
        raise ZevSalesError("ZEV workbook has no ZIP or county sales rows.")
    newest = max([key[1:3] for key in zip_totals] + [key[1:3] for key in county_totals])
    as_of = _quarter_end(newest[0], newest[1])
    zip_sales = tuple(
        ZevZipSales(
            zip_code=zip_code,
            state="CA",
            data_year=year,
            quarter=quarter,
            fuel_type=fuel,
            vehicles=count,
            as_of=as_of,
            source="cec",
        )
        for (zip_code, year, quarter, fuel), count in sorted(zip_totals.items())
    )
    county_sales = tuple(
        ZevCountySales(
            county=county,
            state="CA",
            data_year=year,
            quarter=quarter,
            fuel_type=fuel,
            make=make,
            vehicles=count,
            as_of=as_of,
            source="cec",
        )
        for (county, year, quarter, fuel, make), count in sorted(county_totals.items())
    )
    return ZevSalesBatch(
        as_of=as_of,
        zip_sales=zip_sales,
        county_sales=county_sales,
        source_url=source_url,
        byte_count=len(payload),
    )


def tesla_bev_ratio(
    rows: Sequence[ZevCountySales],
    *,
    year: int | None = None,
    trailing_quarters: int | None = None,
    counties: Sequence[str] | None = None,
) -> float:
    """Return Tesla's share of battery-electric sales over the selected quarters.

    Pass ``year`` for a calendar year, or ``trailing_quarters`` counted back
    from the newest quarter in ``rows``. ``counties`` limits the ratio to
    those county names. ``None`` uses every county in ``rows``.
    """
    selected = _select_periods(
        [(row.data_year, row.quarter) for row in rows],
        year=year,
        trailing_quarters=trailing_quarters,
    )
    allowed = None if counties is None else {name.casefold() for name in counties}
    tesla = 0
    bev = 0
    for row in rows:
        if (row.data_year, row.quarter) not in selected:
            continue
        if row.fuel_type.casefold() != _BEV_FUEL:
            continue
        if allowed is not None and row.county.casefold() not in allowed:
            continue
        bev += row.vehicles
        if row.make.casefold() == "tesla":
            tesla += row.vehicles
    if bev <= 0:
        raise ZevSalesError("No battery-electric county sales in the selected period.")
    return tesla / bev


def resolve_zip_tesla_deliveries(
    state: str,
    *,
    zip_sales: Sequence[ZevZipSales] | None = None,
    county_sales: Sequence[ZevCountySales] | None = None,
    counties: Sequence[str] | None = None,
    year: int | None = None,
    trailing_quarters: int | None = None,
    state_tesla_volume: float | None = None,
    profiles: Sequence[ZipDemandProfile] | None = None,
) -> dict[str, float]:
    """Tesla deliveries per ZIP. California uses CEC sales; other states use the fallback.

    California needs ``zip_sales``, ``county_sales``, and exactly one of
    ``year`` or ``trailing_quarters``. ``counties`` limits the Tesla share
    to that region (the Bay Area tuple is the San Mateo research case).
    Any other state needs ``state_tesla_volume`` and ``profiles``.
    """
    code = state.strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise ZevSalesError(f"State must be 2 letters, got {state!r}.")
    if code == "CA":
        if zip_sales is None or county_sales is None:
            raise ZevSalesError("California Tesla deliveries need CEC ZIP and county sales.")
        share = tesla_bev_ratio(
            county_sales,
            year=year,
            trailing_quarters=trailing_quarters,
            counties=counties,
        )
        return tesla_deliveries_by_zip(
            zip_sales,
            share,
            year=year,
            trailing_quarters=trailing_quarters,
        )
    if state_tesla_volume is None or profiles is None:
        raise ZevSalesError(
            "Outside California, state Tesla volume and ZIP households, income, "
            "and EV share are required."
        )
    return allocate_state_tesla_volume(state_tesla_volume, profiles)


def tesla_deliveries_by_zip(
    rows: Sequence[ZevZipSales],
    tesla_share: float,
    *,
    year: int | None = None,
    trailing_quarters: int | None = None,
) -> dict[str, float]:
    """Allocate ZIP battery-electric sales to Tesla using one share for every ZIP."""
    share = _require_share(tesla_share)
    selected = _select_periods(
        [(row.data_year, row.quarter) for row in rows],
        year=year,
        trailing_quarters=trailing_quarters,
    )
    totals: dict[str, float] = {}
    for row in rows:
        if (row.data_year, row.quarter) not in selected:
            continue
        if row.fuel_type.casefold() != _BEV_FUEL:
            continue
        totals[row.zip_code] = totals.get(row.zip_code, 0.0) + row.vehicles * share
    return totals


def allocate_state_tesla_volume(
    state_tesla_volume: float,
    profiles: Sequence[ZipDemandProfile],
    *,
    income_reference: float = INCOME_REFERENCE,
    ev_share_reference: float = EV_SHARE_REFERENCE,
    income_elasticity: float = INCOME_ELASTICITY,
    ev_share_elasticity: float = EV_SHARE_ELASTICITY,
) -> dict[str, float]:
    """Split a non-California state Tesla total across ZIPs.

    Weight is ``households * (income / income_reference) ** 0.3 * (ev_share /
    ev_share_reference) ** 0.5`` with the defaults above. A ZIP missing
    households, income, EV stock, or light-duty total is omitted. Every
    usable ZIP is returned, including a ZIP whose weight is zero.
    """
    volume = _require_volume(state_tesla_volume)
    income_ref = _positive("income_reference", income_reference)
    ev_ref = _positive("ev_share_reference", ev_share_reference)
    weights: dict[str, float] = {}
    for profile in profiles:
        code = _require_zip(profile.zip_code)
        if code in weights:
            raise ZevSalesError(f"ZIP {code} is listed more than once.")
        weight = _profile_weight(
            profile,
            income_reference=income_ref,
            ev_share_reference=ev_ref,
            income_elasticity=income_elasticity,
            ev_share_elasticity=ev_share_elasticity,
        )
        if weight is None:
            continue
        weights[code] = weight
    scale = sum(weights.values())
    if not weights:
        return {}
    if scale <= 0.0:
        if volume == 0.0:
            return dict.fromkeys(weights, 0.0)
        raise ZevSalesError("Every ZIP weight is zero, so the state volume cannot be split.")
    return {code: volume * weight / scale for code, weight in weights.items()}


def _profile_weight(
    profile: ZipDemandProfile,
    *,
    income_reference: float,
    ev_share_reference: float,
    income_elasticity: float,
    ev_share_elasticity: float,
) -> float | None:
    if (
        profile.households is None
        or profile.median_hh_income is None
        or profile.ev_stock is None
        or profile.total_ldv is None
    ):
        return None
    households = _non_negative("households", profile.households)
    income = _positive("median_hh_income", profile.median_hh_income)
    ev_stock = _non_negative("ev_stock", profile.ev_stock)
    total = _positive("total_ldv", profile.total_ldv)
    if ev_stock > total:
        raise ZevSalesError(
            f"ZIP {profile.zip_code} ev_stock ({ev_stock}) exceeds total_ldv ({total})."
        )
    share = ev_stock / total
    return (
        households
        * (income / income_reference) ** income_elasticity
        * (share / ev_share_reference) ** ev_share_elasticity
    )


def _select_periods(
    periods: Sequence[tuple[int, int]],
    *,
    year: int | None,
    trailing_quarters: int | None,
) -> set[tuple[int, int]]:
    if (year is None) == (trailing_quarters is None):
        raise ZevSalesError("Pass exactly one of year or trailing_quarters.")
    unique = set(periods)
    if year is not None:
        if isinstance(year, bool) or not isinstance(year, int):
            raise ZevSalesError(f"year must be an integer, got {year!r}.")
        return {period for period in unique if period[0] == year}
    if (
        isinstance(trailing_quarters, bool)
        or not isinstance(trailing_quarters, int)
        or trailing_quarters <= 0
    ):
        raise ZevSalesError(
            f"trailing_quarters must be a positive integer, got {trailing_quarters!r}."
        )
    ordered = sorted(unique)
    return set(ordered[-trailing_quarters:])


def _accumulate_zip(rows: Sequence[Mapping[str, str]]) -> dict[tuple[str, int, int, str], int]:
    totals: dict[tuple[str, int, int, str], int] = {}
    for row in rows:
        if _header_row(row):
            continue
        year = _whole(row.get("data_year"), what="Data_Year")
        quarter = _quarter(row.get("quarter"))
        zip_code = _require_zip(_cell(row, "zip", what="ZIP"))
        fuel = _cell(row, "fuel_type", what="FUEL_TYPE")
        count = _whole(row.get("number_of_vehicles"), what="Number of Vehicles")
        key = (zip_code, year, quarter, fuel)
        totals[key] = totals.get(key, 0) + count
    return totals


def _accumulate_county(
    rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, int, int, str, str], int]:
    totals: dict[tuple[str, int, int, str, str], int] = {}
    for row in rows:
        if _header_row(row):
            continue
        year = _whole(row.get("data_year"), what="Data Year")
        quarter = _quarter(row.get("quarter"))
        county = _cell(row, "county", what="COUNTY")
        fuel = _cell(row, "fuel_type", what="FUEL_TYPE")
        make = _cell(row, "make", what="MAKE")
        count = _whole(row.get("number_of_vehicles"), what="Number of Vehicles")
        key = (county, year, quarter, fuel, make)
        totals[key] = totals.get(key, 0) + count
    return totals


def _header_row(row: Mapping[str, str]) -> bool:
    year = row.get("data_year", "")
    return year.casefold() in {"data_year", "data year"}


def _sheet_rows(payload: bytes) -> dict[str, list[dict[str, str]]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ZevSalesError("ZEV download was not an Excel workbook.") from exc
    try:
        shared = _shared_strings(archive)
        paths = _worksheet_paths(archive)
        return {name: _read_sheet(archive, path, shared) for name, path in paths.items()}
    except KeyError as exc:
        raise ZevSalesError("ZEV workbook is missing a required XML part.") from exc


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root:
        if _local(item.tag) != "si":
            continue
        strings.append("".join(node.text or "" for node in item.iter(_NS + "t")))
    return strings


def _worksheet_paths(archive: zipfile.ZipFile) -> dict[str, str]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets: dict[str, str] = {}
    for rel in rels:
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            targets[rel_id] = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
    paths: dict[str, str] = {}
    for sheet in workbook.iter(_NS + "sheet"):
        name = sheet.attrib.get("name")
        rel_id = sheet.attrib.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if name and rel_id and rel_id in targets:
            paths[name] = targets[rel_id]
    return paths


def _read_sheet(archive: zipfile.ZipFile, path: str, shared: Sequence[str]) -> list[dict[str, str]]:
    header: dict[str, str] | None = None
    rows: list[dict[str, str]] = []
    with archive.open(path) as handle:
        for _event, elem in ElementTree.iterparse(handle, events=("end",)):
            if _local(elem.tag) != "row":
                continue
            cells = _row_cells(elem, shared)
            elem.clear()
            if not cells:
                continue
            if header is None:
                header = {column: _norm_header(value) for column, value in cells.items()}
                continue
            record = {
                header[column]: value
                for column, value in cells.items()
                if column in header and header[column] != ""
            }
            if record:
                rows.append(record)
    if header is None:
        raise ZevSalesError(f"Worksheet {path} has no header row.")
    return rows


def _row_cells(row: ElementTree.Element, shared: Sequence[str]) -> dict[str, str]:
    cells: dict[str, str] = {}
    for cell in row:
        if _local(cell.tag) != "c":
            continue
        ref = cell.attrib.get("r", "")
        column = "".join(ch for ch in ref if ch.isalpha())
        if column == "":
            continue
        kind = cell.attrib.get("t")
        if kind == "inlineStr":
            text = "".join(node.text or "" for node in cell.iter(_NS + "t"))
        else:
            node = cell.find(_NS + "v")
            if node is None or node.text is None:
                continue
            if kind == "s":
                text = shared[int(node.text)]
            else:
                text = node.text
        cells[column] = text.strip()
    return cells


def _anchor_texts(html: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    return parser.links


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._parts)))
            self._href = None
            self._parts = []


def _norm_header(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")


def _cell(row: Mapping[str, str], key: str, *, what: str) -> str:
    value = row.get(key)
    if value is None or value.strip() == "":
        raise ZevSalesError(f"ZEV row {what} must be a non-empty string.")
    return value.strip()


def _whole(value: str | None, *, what: str) -> int:
    if value is None or value.strip() == "":
        raise ZevSalesError(f"ZEV row {what} must be a whole number.")
    try:
        number = float(value)
    except ValueError as exc:
        raise ZevSalesError(f"ZEV row {what} is not a number: {value!r}.") from exc
    if not number.is_integer() or number < 0:
        raise ZevSalesError(f"ZEV row {what} must be a whole number >= 0, got {value!r}.")
    return int(number)


def _quarter(value: str | None) -> int:
    quarter = _whole(value, what="Quarter")
    if quarter < 1 or quarter > 4:
        raise ZevSalesError(f"Quarter must be 1, 2, 3, or 4, got {quarter}.")
    return quarter


def _quarter_end(year: int, quarter: int) -> str:
    month, day = _QUARTER_END[quarter]
    return date(year, month, day).isoformat()


def _require_zip(zip_code: str) -> str:
    code = zip_code.strip()
    if len(code) != 5 or not code.isdigit():
        raise ZevSalesError(f"ZIP must be 5 digits, got {zip_code!r}.")
    return code


def _require_share(share: float) -> float:
    if isinstance(share, bool) or not isinstance(share, (int, float)) or not math.isfinite(share):
        raise ZevSalesError(f"Tesla share must be a finite number, got {share!r}.")
    if share < 0 or share > 1:
        raise ZevSalesError(f"Tesla share must be between 0 and 1, got {share}.")
    return float(share)


def _require_volume(volume: float) -> float:
    if (
        isinstance(volume, bool)
        or not isinstance(volume, (int, float))
        or not math.isfinite(volume)
    ):
        raise ZevSalesError(f"State Tesla volume must be a finite number, got {volume!r}.")
    if volume < 0:
        raise ZevSalesError(f"State Tesla volume must be >= 0, got {volume}.")
    return float(volume)


def _positive(what: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ZevSalesError(f"{what} must be a finite number, got {value!r}.")
    if value <= 0:
        raise ZevSalesError(f"{what} must be > 0, got {value}.")
    return float(value)


def _non_negative(what: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ZevSalesError(f"{what} must be a finite number, got {value!r}.")
    if value < 0:
        raise ZevSalesError(f"{what} must be >= 0, got {value}.")
    return float(value)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
