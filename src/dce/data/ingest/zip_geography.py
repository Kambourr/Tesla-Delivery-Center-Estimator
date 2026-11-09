"""Build a nationwide ZIP to ZCTA, county, and CBSA crosswalk.

Census does not publish a USPS ZIP Code to ZCTA file. A ZCTA code is itself
a USPS ZIP Code, and not every ZIP Code is a ZCTA (post-office boxes and
single-delivery points have no polygon). This module combines three public
files:

* the Census 2020 ZCTA-to-county relationship (land-area share)
* the Census CBSA delineation (July 2023 list 1), including metropolitan
  divisions
* the HRSA GeoCare Navigator ZIP-to-ZCTA crosswalk for ZIP Codes that are
  not ZCTAs

``GeoContext.cbsa`` is the metropolitan division when the delineation file
has one, and the CBSA otherwise. That matches the HUD ZIP-CBSA column for
94401–94404 (division ``41884``, not parent ``41860``). A county that is
not in any metro or micro area has an empty ``cbsa``.

No SQLite and no network. The build script downloads the files.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from dce.data.ingest.http import IngestError

STATE_ABBR: dict[str, str] = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
    "60": "AS",
    "66": "GU",
    "69": "MP",
    "72": "PR",
    "78": "VI",
}


class ZipGeographyError(IngestError):
    """A crosswalk input could not be turned into ZIP rows."""


@dataclass(frozen=True)
class ZctaCountyPart:
    """One ZCTA overlap with a county. ``land_sqm`` is the overlap, not the whole ZCTA."""

    zcta: str
    county_fips: str
    county_name: str
    land_sqm: int


@dataclass(frozen=True)
class CountyCbsa:
    """County assignment from the CBSA delineation file."""

    county_fips: str
    cbsa: str
    cbsa_name: str
    parent_cbsa: str
    parent_name: str
    metropolitan: bool


@dataclass(frozen=True)
class HrsaZipZcta:
    """One HRSA ZIP-to-ZCTA row. ``zcta`` is blank when HRSA has no match."""

    zip_code: str
    zcta: str
    state: str
    join_type: str


@dataclass(frozen=True)
class ZipCrosswalkRow:
    """One ZIP-county row. ``tot_ratio`` is the ZCTA's land share in that county.

    For a ZIP that is not a ZCTA, ``tot_ratio`` is 1 and the county is the
    dominant county of the HRSA ZCTA.
    """

    zip_code: str
    zcta: str
    county_fips: str
    county_name: str
    cbsa: str
    cbsa_name: str
    state: str
    tot_ratio: float


def parse_zcta_county_relationship(text: str) -> tuple[ZctaCountyPart, ...]:
    """Parse ``tab20_zcta520_county20_natl.txt``. Rows with no ZCTA are dropped."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ZipGeographyError("ZCTA-county relationship file has no data rows.")
    header = lines[0].split("|")
    index = _header_index(
        header,
        ("GEOID_ZCTA5_20", "GEOID_COUNTY_20", "NAMELSAD_COUNTY_20", "AREALAND_PART"),
    )
    rows: list[ZctaCountyPart] = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) <= max(index.values()):
            raise ZipGeographyError("ZCTA-county row is shorter than the header.")
        zcta = parts[index["GEOID_ZCTA5_20"]].strip()
        if len(zcta) != 5 or not zcta.isdigit():
            continue
        county = _fips(parts[index["GEOID_COUNTY_20"]], width=5, what="county")
        name = parts[index["NAMELSAD_COUNTY_20"]].strip()
        if name == "":
            raise ZipGeographyError(f"ZCTA {zcta} county {county} has no name.")
        rows.append(
            ZctaCountyPart(
                zcta=zcta,
                county_fips=county,
                county_name=name,
                land_sqm=_whole(parts[index["AREALAND_PART"]], what=f"ZCTA {zcta} land"),
            )
        )
    if not rows:
        raise ZipGeographyError("ZCTA-county relationship file has no ZCTA rows.")
    return tuple(rows)


def parse_cbsa_delineation(table: Sequence[Sequence[str]]) -> tuple[CountyCbsa, ...]:
    """Parse Census list-1 rows. The header row is the one that starts with ``CBSA Code``."""
    header_at = next(
        (index for index, row in enumerate(table) if row and row[0].strip() == "CBSA Code"),
        None,
    )
    if header_at is None:
        raise ZipGeographyError("CBSA delineation file has no CBSA Code header.")
    header = [cell.strip() for cell in table[header_at]]
    index = _header_index(
        header,
        (
            "CBSA Code",
            "Metropolitan Division Code",
            "CBSA Title",
            "Metropolitan Division Title",
            "Metropolitan/Micropolitan Statistical Area",
            "FIPS State Code",
            "FIPS County Code",
        ),
    )
    rows: list[CountyCbsa] = []
    seen: set[str] = set()
    for raw in table[header_at + 1 :]:
        cells = list(raw)
        if not any(cell.strip() for cell in cells):
            continue
        parent_text = _cell(cells, index["CBSA Code"])
        if not _looks_like_area(parent_text):
            continue
        parent = _code(cells, index["CBSA Code"], what="CBSA")
        division = _optional_code(cells, index["Metropolitan Division Code"])
        state = _fips(_cell(cells, index["FIPS State Code"]), width=2, what="state")
        county3 = _fips(_cell(cells, index["FIPS County Code"]), width=3, what="county")
        county = state + county3
        if county in seen:
            continue
        seen.add(county)
        parent_name = _cell(cells, index["CBSA Title"]).strip()
        division_name = _cell(cells, index["Metropolitan Division Title"]).strip()
        kind = _cell(cells, index["Metropolitan/Micropolitan Statistical Area"]).strip()
        rows.append(
            CountyCbsa(
                county_fips=county,
                cbsa=division or parent,
                cbsa_name=division_name or parent_name,
                parent_cbsa=parent,
                parent_name=parent_name,
                metropolitan=kind.startswith("Metro"),
            )
        )
    if not rows:
        raise ZipGeographyError("CBSA delineation file has no county rows.")
    return tuple(rows)


def parse_hrsa_zip_zcta(table: Sequence[Sequence[str]]) -> tuple[HrsaZipZcta, ...]:
    """Parse the HRSA ZIP Code to ZCTA workbook. A blank ZCTA is kept and later skipped."""
    if not table:
        raise ZipGeographyError("HRSA crosswalk has no rows.")
    header = [cell.strip() for cell in table[0]]
    index = _header_index(header, ("ZIP_CODE", "STATE", "ZCTA", "ZIP_JOIN_TYPE"))
    rows: list[HrsaZipZcta] = []
    seen: set[str] = set()
    for raw in table[1:]:
        cells = list(raw)
        zip_code = _zip(_cell(cells, index["ZIP_CODE"]))
        if zip_code in seen:
            continue
        seen.add(zip_code)
        zcta_text = _cell(cells, index["ZCTA"]).strip()
        zcta = ""
        if zcta_text != "" and zcta_text.casefold() != "no zcta":
            zcta = _zip(zcta_text)
        state = _cell(cells, index["STATE"]).strip().upper()
        if len(state) != 2 or not state.isalpha():
            raise ZipGeographyError(f"HRSA ZIP {zip_code} has no 2-letter state.")
        rows.append(
            HrsaZipZcta(
                zip_code=zip_code,
                zcta=zcta,
                state=state,
                join_type=_cell(cells, index["ZIP_JOIN_TYPE"]).strip(),
            )
        )
    if not rows:
        raise ZipGeographyError("HRSA crosswalk has no ZIP rows.")
    return tuple(rows)


def division_parents(counties: Sequence[CountyCbsa]) -> dict[str, str]:
    """Map a metropolitan division code to its parent CBSA. Divisions only."""
    found: dict[str, str] = {}
    for county in counties:
        if county.cbsa != county.parent_cbsa:
            found[county.cbsa] = county.parent_cbsa
    return found


def assemble_zip_crosswalk(
    parts: Sequence[ZctaCountyPart],
    counties: Mapping[str, CountyCbsa],
    hrsa: Sequence[HrsaZipZcta] = (),
) -> tuple[ZipCrosswalkRow, ...]:
    """Return one row per ZIP and county.

    ZCTA codes are their own ZIP. ``tot_ratio`` is that county's share of the
    ZCTA land area. HRSA then adds ZIP Codes that are not ZCTAs, pointed at
    the ZCTA and at that ZCTA's dominant county.
    """
    grouped: dict[str, list[ZctaCountyPart]] = {}
    for part in parts:
        grouped.setdefault(part.zcta, []).append(part)
    rows: list[ZipCrosswalkRow] = []
    dominant: dict[str, ZipCrosswalkRow] = {}
    for zcta in sorted(grouped):
        group = grouped[zcta]
        positive = [part for part in group if part.land_sqm > 0]
        chosen = positive or list(group)
        total = sum(part.land_sqm for part in chosen)
        best: ZipCrosswalkRow | None = None
        for part in chosen:
            share = part.land_sqm / total if total > 0 else 1.0 / len(chosen)
            row = _row_for_part(part, share, counties)
            if row is None:
                continue
            rows.append(row)
            if _prefer(row, best):
                best = row
        if best is not None:
            dominant[zcta] = best
    known = {row.zip_code for row in rows}
    for item in hrsa:
        if item.zip_code in known or item.zcta == "":
            continue
        base = dominant.get(item.zcta)
        if base is None:
            continue
        rows.append(
            ZipCrosswalkRow(
                zip_code=item.zip_code,
                zcta=item.zcta,
                county_fips=base.county_fips,
                county_name=base.county_name,
                cbsa=base.cbsa,
                cbsa_name=base.cbsa_name,
                state=base.state,
                tot_ratio=1.0,
            )
        )
        known.add(item.zip_code)
    if not rows:
        raise ZipGeographyError("Crosswalk assembly produced no ZIP rows.")
    rows.sort(key=lambda row: (row.zip_code, -row.tot_ratio, row.county_fips))
    return tuple(rows)


def _row_for_part(
    part: ZctaCountyPart,
    share: float,
    counties: Mapping[str, CountyCbsa],
) -> ZipCrosswalkRow | None:
    state = STATE_ABBR.get(part.county_fips[:2])
    if state is None:
        return None
    assignment = counties.get(part.county_fips)
    return ZipCrosswalkRow(
        zip_code=part.zcta,
        zcta=part.zcta,
        county_fips=part.county_fips,
        county_name=part.county_name,
        cbsa="" if assignment is None else assignment.cbsa,
        cbsa_name="" if assignment is None else assignment.cbsa_name,
        state=state,
        tot_ratio=round(share, 8),
    )


def _prefer(candidate: ZipCrosswalkRow, current: ZipCrosswalkRow | None) -> bool:
    if current is None:
        return True
    if candidate.tot_ratio != current.tot_ratio:
        return candidate.tot_ratio > current.tot_ratio
    return candidate.county_fips < current.county_fips


def _header_index(header: Sequence[str], required: Sequence[str]) -> dict[str, int]:
    index = {name: position for position, name in enumerate(header)}
    missing = [name for name in required if name not in index]
    if missing:
        raise ZipGeographyError("Missing column " + ", ".join(missing) + ".")
    return index


def _cell(cells: Sequence[str], index: int) -> str:
    if index >= len(cells):
        return ""
    return cells[index]


def _fips(value: str, *, width: int, what: str) -> str:
    text = value.strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < width:
        text = text.zfill(width)
    if len(text) != width or not text.isdigit():
        raise ZipGeographyError(f"{what} FIPS must be {width} digits, got {value!r}.")
    return text


def _looks_like_area(value: str) -> bool:
    text = value.strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.isdigit() and len(text) <= 5


def _code(cells: Sequence[str], index: int, *, what: str) -> str:
    text = _optional_code(cells, index)
    if text == "":
        raise ZipGeographyError(f"{what} code is blank.")
    return text


def _optional_code(cells: Sequence[str], index: int) -> str:
    text = _cell(cells, index).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text == "":
        return ""
    if text.isdigit() and len(text) < 5:
        text = text.zfill(5)
    if len(text) != 5 or not text.isdigit():
        raise ZipGeographyError(f"Area code must be 5 digits, got {text!r}.")
    return text


def _zip(value: str) -> str:
    text = value.strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) < 5:
        text = text.zfill(5)
    if len(text) != 5 or not text.isdigit():
        raise ZipGeographyError(f"ZIP must be 5 digits, got {value!r}.")
    return text


def _whole(value: str, *, what: str) -> int:
    text = value.strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if not text.isdigit():
        raise ZipGeographyError(f"{what} must be a whole number, got {value!r}.")
    return int(text)
