"""Build the committed electricity, property-tax, price-index, and construction-cost seeds.

Runtime ``estimate`` reads the CSVs this script writes. It does not download
them. Re-run the script only when refreshing the public files in ``--cache``.

Inputs, all public:

- EIA Electric Power Monthly table 5.6.A (commercial cents/kWh by state).
- EIA-861 2024 sales to ultimate customers and service territories.
- BEA Regional Price Parities, 2024 (SARPP and MARPP). Fit-out fallback only.
- Lincoln Institute / Minnesota Center for Fiscal Excellence, 50-State
  Property Tax Comparison Study, taxes paid in 2024 (July 2025). The script
  reads ``pdftotext -layout`` output of the study PDF (``--lincoln-text``)
  and parses Appendix Tables 3a, 3b, and 3c (commercial: $1 million land and
  building plus $200,000 of fixtures) and 4a, 4c, and 4e (industrial: $1
  million real property plus $1 million of personal property). The PDF is
  not stored in git.
- DoD UFS 3-701-01 Facilities Pricing Guide, 6 June 2026, data tables
  workbook, sheet ``Table 4-1 CONUS`` (MILCON area cost factors, source date
  2025-10-01). ``--dod-xlsx``.

PG&E Schedule B-10 is applied later by the resolver for utility 14328.
This script still stores that utility's EIA-861 average so the ladder has
both rungs.
"""

from __future__ import annotations

import argparse
import csv
import re
import statistics
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dce.data.ingest.xlsx_table import read_xlsx_rows  # noqa: E402

SEED = ROOT / "data" / "seed"
CROSSWALK = SEED / "zip_crosswalk.csv"

EPM_AS_OF = "2026-08-31"
EPM_CITATION = (
    "EIA Electric Power Monthly Table 5.6.A, commercial, August 2026. "
    "https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_5_6_a"
)
EIA861_AS_OF = "2024-12-31"
EIA861_CITATION = (
    "EIA-861 2024 commercial revenue / (bundled + delivery MWh). "
    "https://www.eia.gov/electricity/data/eia861/"
)
PGE_UTILITY_ID = "14328"
PGE_AS_OF = "2026-03-01"
PGE_CITATION = (
    "PG&E Schedule B-10, effective 2026-03-01. "
    "https://www.pge.com/tariffs/assets/pdf/tariffbook/ELEC_SCHEDS_B-10.pdf"
)
BEA_AS_OF = "2024-12-31"
BEA_CITATION = (
    "BEA Regional Price Parities, 2024, released 2026-02-19. US all-items = 100. "
    "https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area"
)
TAX_AS_OF = "2024-12-31"
TAX_CITATION = (
    "Lincoln Institute and Minnesota Center for Fiscal Excellence, 50-State "
    "Property Tax Comparison Study, taxes paid in 2024 (July 2025). "
    "https://www.lincolninst.edu/publications/other/50-state-property-tax-comparison-study-2024/"
)
ACF_AS_OF = "2025-10-01"
ACF_SOURCE = "dod_ufs_3_701_01_2026"
ACF_SHEET = "Table 4-1 CONUS"
ACF_CITATION = "DoD UFS 3-701-01 (6 June 2026) Table 4-1 CONUS, MILCON area cost factor"
ACF_URL = "https://legacy.wbdg.org/FFC/DOD/UFC/ufs_3_701_01_2026_Data_Tables.xlsx"

# Postal abbreviations. EIA table 5.6.A uses these names. Census divisions are skipped.
STATE_NAMES = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "District of Columbia": "DC",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}

# BEA state GeoFIPS (SS000) to postal.
FIPS_TO_POSTAL = {
    "01000": "AL",
    "02000": "AK",
    "04000": "AZ",
    "05000": "AR",
    "06000": "CA",
    "08000": "CO",
    "09000": "CT",
    "10000": "DE",
    "11000": "DC",
    "12000": "FL",
    "13000": "GA",
    "15000": "HI",
    "16000": "ID",
    "17000": "IL",
    "18000": "IN",
    "19000": "IA",
    "20000": "KS",
    "21000": "KY",
    "22000": "LA",
    "23000": "ME",
    "24000": "MD",
    "25000": "MA",
    "26000": "MI",
    "27000": "MN",
    "28000": "MS",
    "29000": "MO",
    "30000": "MT",
    "31000": "NE",
    "32000": "NV",
    "33000": "NH",
    "34000": "NJ",
    "35000": "NM",
    "36000": "NY",
    "37000": "NC",
    "38000": "ND",
    "39000": "OH",
    "40000": "OK",
    "41000": "OR",
    "42000": "PA",
    "44000": "RI",
    "45000": "SC",
    "46000": "SD",
    "47000": "TN",
    "48000": "TX",
    "49000": "UT",
    "50000": "VT",
    "51000": "VA",
    "53000": "WA",
    "54000": "WV",
    "55000": "WI",
    "56000": "WY",
}

# Lincoln study rules.
#
# state_urban is the largest city (Appendix Table 3a), except Illinois
# (Aurora, not Chicago) and New York (Buffalo, not New York City): the study
# says those two cities' systems differ from the rest of the state. The same
# two cities never stand in for a neighbouring county (metro_proxy false).
# state_rural is Appendix Table 3c. DC has no rural analogue; its rural rung
# repeats the city.
STATE_URBAN_OVERRIDE = {"IL": "Aurora", "NY": "Buffalo"}
NO_METRO_PROXY = {("IL", "Chicago"), ("NY", "New York City")}
# Appendix Table 4g, "Fixtures: Full Exemption" (15 cities in 13 states, plus
# the second IL and NY cities). Montana's first $1 million of personal property
# is exempt (Table 4g note), which covers the $200,000 of fixtures on the $1
# million parcel. Vermont's rural municipality, Hartford, fully exempts
# fixtures (Table 4g rural note); Burlington does not. Where fixtures are
# exempt, the commercial tax bill falls on the $1 million of real property
# only, so the rate on real property is that bill / $1 million. Elsewhere the
# published rate on $1.2 million is kept.
FIXTURES_EXEMPT_STATES = {
    "DE", "HI", "IL", "IA", "MA", "MN", "MT", "NH", "NJ", "NY", "ND", "OH", "PA", "SD"
}  # fmt: skip
FIXTURES_EXEMPT_RURAL = {"VT"}
LINCOLN_COUNTS = {"3a": 53, "3b": 50, "3c": 50}
LINCOLN_INDUSTRIAL = {"3a": "4a", "3b": "4c", "3c": "4e"}
LINCOLN_NATIONAL_COMMERCIAL_PERCENT = 1.755  # Table 3a average, 53 cities, $1 million
LINCOLN_NATIONAL_INDUSTRIAL_PERCENT = 1.250  # Table 4a average, 53 cities, $1 million
# Leads that pdftotext wraps across lines.
LINCOLN_LEAD_FIXUPS = {"New Lancaster": ("NH", "Lancaster")}
LINCOLN_CITY_ALIASES = {"Maurice River Twp": "Maurice River Township"}
# Studied places keyed by the Census county name in zip_crosswalk.csv.
# When two studied cities share a county, the larger city is the one kept
# (Phoenix not Mesa, Los Angeles not Long Beach, Fort Worth not Arlington).
# Percent, same $1 million commercial definition.
COUNTY_PLACES: tuple[tuple[str, str, str, float], ...] = (
    ("AL", "Madison County", "Huntsville", 1.442),
    ("AL", "Monroe County", "Monroeville", 0.795),
    ("AK", "Anchorage Municipality", "Anchorage", 1.426),
    ("AK", "Ketchikan Gateway Borough", "Ketchikan", 1.043),
    ("AZ", "Maricopa County", "Phoenix", 1.620),
    ("AZ", "Pima County", "Tucson", 1.541),
    ("AZ", "Graham County", "Safford", 0.811),
    ("AR", "Pulaski County", "Little Rock", 1.366),
    ("AR", "Randolph County", "Pocahontas", 0.819),
    ("CA", "Los Angeles County", "Los Angeles", 1.200),
    ("CA", "Kern County", "Bakersfield", 1.177),
    ("CA", "Fresno County", "Fresno", 1.267),
    ("CA", "Alameda County", "Oakland", 1.260),
    ("CA", "Sacramento County", "Sacramento", 1.152),
    ("CA", "San Diego County", "San Diego", 1.228),
    ("CA", "San Francisco County", "San Francisco", 1.171),
    ("CA", "Santa Clara County", "San Jose", 1.278),
    ("CA", "Siskiyou County", "Yreka", 1.065),
    ("CO", "Denver County", "Denver", 2.106),
    ("CO", "El Paso County", "Colorado Springs", 1.477),
    ("CO", "Huerfano County", "Walsenburg", 2.414),
    ("CT", "Fairfield County", "Bridgeport", 2.309),
    ("CT", "Litchfield County", "Litchfield", 0.983),
    ("DE", "New Castle County", "Wilmington", 0.846),
    ("DE", "Sussex County", "Georgetown", 0.362),
    ("DC", "District of Columbia", "Washington", 1.129),
    ("FL", "Duval County", "Jacksonville", 1.635),
    ("FL", "Miami-Dade County", "Miami", 1.803),
    ("FL", "Hillsborough County", "Tampa", 1.709),
    ("FL", "Glades County", "Moore Haven", 2.006),
    ("GA", "Fulton County", "Atlanta", 1.505),
    ("GA", "Ben Hill County", "Fitzgerald", 1.672),
    ("HI", "Honolulu County", "Honolulu", 1.052),
    ("HI", "Kauai County", "Kauai", 0.675),
    ("ID", "Ada County", "Boise", 0.751),
    ("ID", "Fremont County", "Saint Anthony", 0.668),
    ("IL", "Cook County", "Chicago", 3.620),
    ("IL", "Kane County", "Aurora", 2.608),
    ("IL", "Jo Daviess County", "Galena", 2.525),
    ("IN", "Marion County", "Indianapolis", 2.550),
    ("IN", "Jennings County", "North Vernon", 2.838),
    ("IA", "Polk County", "Des Moines", 2.695),
    ("IA", "Franklin County", "Hampton", 2.827),
    ("KS", "Sedgwick County", "Wichita", 2.387),
    ("KS", "Allen County", "Iola", 3.808),
    ("KY", "Jefferson County", "Louisville", 1.283),
    ("KY", "Rowan County", "Morehead", 1.168),
    ("LA", "Orleans Parish", "New Orleans", 1.714),
    ("LA", "Natchitoches Parish", "Natchitoches", 1.314),
    ("ME", "Cumberland County", "Portland", 1.376),
    ("ME", "Knox County", "Rockland", 1.958),
    ("MD", "Baltimore city", "Baltimore", 2.823),
    ("MD", "Caroline County", "Denton", 2.023),
    ("MA", "Suffolk County", "Boston", 2.106),
    ("MA", "Berkshire County", "Adams", 1.938),
    ("MI", "Wayne County", "Detroit", 3.996),
    ("MI", "Schoolcraft County", "Manistique", 2.711),
    ("MN", "Hennepin County", "Minneapolis", 2.355),
    ("MN", "McLeod County", "Glencoe", 2.255),
    ("MS", "Hinds County", "Jackson", 2.745),
    ("MS", "Neshoba County", "Philadelphia", 2.064),
    ("MO", "Jackson County", "Kansas City", 2.750),
    ("MO", "Cooper County", "Boonville", 2.444),
    ("MT", "Yellowstone County", "Billings", 0.786),
    ("MT", "Valley County", "Glasgow", 0.957),
    ("NE", "Douglas County", "Omaha", 1.838),
    ("NE", "Cheyenne County", "Sidney", 2.033),
    ("NV", "Clark County", "Las Vegas", 1.131),
    ("NV", "Churchill County", "Fallon", 1.257),
    ("NH", "Hillsborough County", "Manchester", 1.232),
    ("NH", "Coos County", "Lancaster", 1.592),
    ("NJ", "Essex County", "Newark", 1.770),
    ("NJ", "Cumberland County", "Maurice River Township", 1.981),
    ("NM", "Bernalillo County", "Albuquerque", 1.685),
    ("NM", "Guadalupe County", "Santa Rosa", 1.088),
    ("NY", "Erie County", "Buffalo", 1.640),
    ("NY", "New York County", "New York City", 1.418),
    ("NY", "Kings County", "New York City", 1.418),
    ("NY", "Queens County", "New York City", 1.418),
    ("NY", "Bronx County", "New York City", 1.418),
    ("NY", "Richmond County", "New York City", 1.418),
    ("NY", "Wyoming County", "Warsaw", 2.383),
    ("NC", "Mecklenburg County", "Charlotte", 0.711),
    ("NC", "Wake County", "Raleigh", 0.793),
    ("NC", "Chowan County", "Edenton", 0.913),
    ("ND", "Cass County", "Fargo", 1.121),
    ("ND", "Ramsey County", "Devils Lake", 1.370),
    ("OH", "Franklin County", "Columbus", 1.909),
    ("OH", "Williams County", "Bryan", 1.425),
    ("OK", "Oklahoma County", "Oklahoma City", 1.420),
    ("OK", "Tulsa County", "Tulsa", 1.403),
    ("OK", "Greer County", "Mangum", 1.007),
    ("OR", "Multnomah County", "Portland", 2.593),
    ("OR", "Tillamook County", "Tillamook", 1.136),
    ("PA", "Philadelphia County", "Philadelphia", 1.977),
    ("PA", "Elk County", "Ridgway", 1.870),
    ("RI", "Providence County", "Providence", 3.070),
    ("RI", "Washington County", "Hopkinton", 1.404),
    ("SC", "Charleston County", "Charleston", 1.937),
    ("SC", "Marion County", "Mullins", 2.985),
    ("SD", "Minnehaha County", "Sioux Falls", 1.187),
    ("SD", "Clay County", "Vermillion", 1.433),
    ("TN", "Davidson County", "Nashville", 0.937),
    ("TN", "Shelby County", "Memphis", 1.995),
    ("TN", "Hardin County", "Savannah", 0.939),
    ("TX", "Harris County", "Houston", 1.997),
    ("TX", "Tarrant County", "Fort Worth", 2.088),
    ("TX", "Travis County", "Austin", 1.808),
    ("TX", "Dallas County", "Dallas", 2.118),
    ("TX", "El Paso County", "El Paso", 2.544),
    ("TX", "Bexar County", "San Antonio", 2.347),
    ("TX", "Pecos County", "Fort Stockton", 2.066),
    ("UT", "Salt Lake County", "Salt Lake City", 0.928),
    ("UT", "Sevier County", "Richfield", 0.964),
    ("VT", "Chittenden County", "Burlington", 2.261),
    ("VT", "Windsor County", "Hartford", 2.372),
    ("VA", "Virginia Beach city", "Virginia Beach", 0.873),
    ("VA", "Wise County", "Wise", 0.868),
    ("WA", "King County", "Seattle", 0.785),
    ("WA", "Okanogan County", "Okanogan", 0.862),
    ("WV", "Kanawha County", "Charleston", 1.856),
    ("WV", "Randolph County", "Elkins", 1.171),
    ("WI", "Milwaukee County", "Milwaukee", 1.959),
    ("WI", "Barron County", "Rice Lake", 1.723),
    ("WY", "Laramie County", "Cheyenne", 0.599),
    ("WY", "Washakie County", "Worland", 0.743),
)


SEEDS = ("electricity", "property-tax", "price-index", "construction-cost")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/dce-public"))
    parser.add_argument(
        "--lincoln-text",
        type=Path,
        default=None,
        help="pdftotext -layout output of the Lincoln 2024 study PDF. "
        "Default: <cache>/lincoln_50_state_2024_layout.txt",
    )
    parser.add_argument(
        "--dod-xlsx",
        type=Path,
        default=None,
        help="UFS 3-701-01 2026 data tables workbook. "
        "Default: <cache>/ufs_3_701_01_2026_Data_Tables.xlsx",
    )
    parser.add_argument(
        "--only",
        choices=SEEDS,
        action="append",
        help="Write only this seed. Repeat for more than one. Default: all.",
    )
    args = parser.parse_args()
    cache: Path = args.cache
    only = set(args.only or SEEDS)
    if "electricity" in only:
        write_electricity(cache)
    if "property-tax" in only:
        write_property_tax(args.lincoln_text or cache / "lincoln_50_state_2024_layout.txt")
    if "price-index" in only:
        write_rpp(cache)
    if "construction-cost" in only:
        write_construction_cost(args.dod_xlsx or cache / "ufs_3_701_01_2026_Data_Tables.xlsx")
    print("wrote seeds under", SEED)


def write_electricity(cache: Path) -> None:
    epm = _epm_prices(cache / "table_5_06_a.xlsx")
    sales = _utility_prices(cache / "eia861" / "Sales_Ult_Cust_2024.xlsx")
    territory = _territory(cache / "eia861" / "Service_Territory_2024.xlsx")
    counties = _crosswalk_counties()
    chosen, unmatched, ambiguous = _assign_counties(territory, sales, counties)

    rate_rows: list[dict[str, str]] = []
    us = epm["US"]
    rate_rows.append(
        _rate(
            "national", "US", "United States", us, "", "average", EPM_AS_OF, "eia_epm", EPM_CITATION
        )
    )
    for postal in sorted(STATE_NAMES.values()):
        cents = epm[postal]
        name = next(label for label, code in STATE_NAMES.items() if code == postal)
        rate_rows.append(
            _rate("state", postal, name, cents, "", "average", EPM_AS_OF, "eia_epm", EPM_CITATION)
        )
    for utility_id in sorted(sales, key=lambda item: int(item)):
        price, name = sales[utility_id]
        rate_rows.append(
            _rate(
                "utility",
                utility_id,
                name,
                0.0,
                "",
                "average",
                EIA861_AS_OF,
                "eia861",
                EIA861_CITATION,
                energy_dollars=price,
            )
        )
    pge_name = sales[PGE_UTILITY_ID][1]
    rate_rows.append(
        _rate(
            "utility",
            PGE_UTILITY_ID,
            pge_name,
            28.75,
            "20.5",
            "B-10",
            PGE_AS_OF,
            "pge_pdf",
            PGE_CITATION,
        )
    )
    _write_csv(
        SEED / "electricity_commercial.csv",
        (
            "level",
            "geo_id",
            "name",
            "energy_rate_kwh",
            "demand_rate_kw",
            "schedule",
            "as_of",
            "source",
            "citation",
        ),
        rate_rows,
    )
    county_rows = [
        {
            "county_fips": fips,
            "utility_id": utility_id,
            "utility_name": sales[utility_id][1],
            "commercial_mwh": f"{mwh:.0f}",
        }
        for fips, (utility_id, mwh) in sorted(chosen.items())
    ]
    _write_csv(
        SEED / "county_utility.csv",
        ("county_fips", "utility_id", "utility_name", "commercial_mwh"),
        county_rows,
    )
    print(
        f"electricity: {len(rate_rows)} rates, {len(county_rows)} counties, "
        f"{unmatched} EIA counties unmatched, {ambiguous} ambiguous"
    )
    for label, fips in (
        ("San Mateo", "06081"),
        ("Travis", "48453"),
        ("Miami-Dade", "12086"),
        ("New York", "36061"),
        ("Washakie", "56043"),
    ):
        hit = chosen.get(fips)
        print(f"  {label} {fips}: {hit}")


@dataclass(frozen=True)
class LincolnRow:
    """One $1 million parcel row of a Lincoln appendix table."""

    table: str
    state: str
    city: str
    percent: float
    bill: int


_LINCOLN_HEAD = re.compile(r"^\s*Appendix Table (\d[a-h]):")
_LINCOLN_CELL = re.compile(r"(\d+\.\d{3})%\s+([\d,]+)")


def lincoln_tables(text: str) -> dict[str, list[LincolnRow]]:
    """Parse the $1 million columns of Appendix Tables 3a-3c and 4a, 4c, 4e.

    Each data line has three ``rate% bill`` cells: $100,000, $1 million, and
    $25 million. The middle one is kept. Industrial rows are matched to the
    commercial table by position (both tables list the same places in the
    same order) and the matched city is checked against the industrial lead.
    """
    lines = text.splitlines()
    starts: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = _LINCOLN_HEAD.match(line)
        if match and match.group(1) not in starts:
            starts[match.group(1)] = index
    raw: dict[str, list[tuple[str, float, int]]] = {}
    for table in (*LINCOLN_COUNTS, *LINCOLN_INDUSTRIAL.values()):
        if table not in starts:
            raise SystemExit(f"Lincoln text has no Appendix Table {table}")
        begin = starts[table]
        end = min((at for at in starts.values() if at > begin), default=len(lines))
        found: list[tuple[str, float, int]] = []
        for line in lines[begin:end]:
            cells = _LINCOLN_CELL.findall(line)
            if len(cells) < 3 or "AVERAGE" in line.upper():
                continue
            lead = " ".join(line[: line.index(cells[0][0] + "%")].split())
            found.append((lead, float(cells[1][0]), int(cells[1][1].replace(",", ""))))
        raw[table] = found
    tables: dict[str, list[LincolnRow]] = {}
    names = {**STATE_NAMES, "DC": "DC"}
    for table, expected in LINCOLN_COUNTS.items():
        if len(raw[table]) != expected:
            raise SystemExit(f"Table {table}: {len(raw[table])} rows, expected {expected}")
        parsed: list[LincolnRow] = []
        for lead, percent, bill in raw[table]:
            state, city = _lincoln_place(lead, names)
            parsed.append(LincolnRow(table, state, city, percent, bill))
        tables[table] = parsed
        industrial = LINCOLN_INDUSTRIAL[table]
        if len(raw[industrial]) != expected:
            raise SystemExit(
                f"Table {industrial}: {len(raw[industrial])} rows, expected {expected}"
            )
        matched: list[LincolnRow] = []
        for place, (lead, percent, bill) in zip(parsed, raw[industrial], strict=True):
            last = lead.replace("*", "").split()[-1] if lead else ""
            if last not in place.city.split() and last not in place.city:
                raise SystemExit(f"Table {industrial} row {lead!r} is not {place.city}")
            matched.append(LincolnRow(industrial, place.state, place.city, percent, bill))
        tables[industrial] = matched
    return tables


def _lincoln_place(lead: str, names: dict[str, str]) -> tuple[str, str]:
    if lead in LINCOLN_LEAD_FIXUPS:
        return LINCOLN_LEAD_FIXUPS[lead]
    for name in sorted(names, key=len, reverse=True):
        if lead.startswith(name + " "):
            city = lead[len(name) :].replace("*", "").strip()
            return names[name], LINCOLN_CITY_ALIASES.get(city, city)
    raise SystemExit(f"Lincoln row lead {lead!r} has no state")


def write_property_tax(lincoln_text: Path) -> None:
    tables = lincoln_tables(lincoln_text.read_text(encoding="utf-8"))
    industrial: dict[tuple[str, str, str], LincolnRow] = {}
    for table, partner in LINCOLN_INDUSTRIAL.items():
        for commercial_row, industrial_row in zip(tables[table], tables[partner], strict=True):
            industrial[(table, commercial_row.state, commercial_row.city)] = industrial_row
    counties = _crosswalk_counties()
    county_cbsa = _crosswalk_county_cbsa()
    by_name = {(state, name): fips for fips, (state, name) in counties.items()}

    urban: dict[str, LincolnRow] = {}
    for row in tables["3a"]:
        if (row.state, row.city) in NO_METRO_PROXY:
            continue
        if STATE_URBAN_OVERRIDE.get(row.state, row.city) == row.city:
            urban[row.state] = row
    rural = {row.state: row for row in tables["3c"]}
    rural.setdefault("DC", urban["DC"])
    lookup: dict[tuple[str, str], LincolnRow] = {}
    for table in ("3b", "3a", "3c"):
        for row in tables[table]:
            lookup[(row.state, row.city)] = row

    effective_3a = [_real_rate(row) for row in tables["3a"]]
    published_3a = statistics.fmean(row.percent for row in tables["3a"])
    if abs(published_3a - LINCOLN_NATIONAL_COMMERCIAL_PERCENT) > 0.001:
        raise SystemExit(f"Table 3a mean {published_3a:.4f}% is not the study average")
    rows: list[dict[str, str]] = [
        {
            "level": "national",
            "state": "US",
            "county_fips": "",
            "cbsa": "",
            "place": "53-city average",
            "effective_rate": f"{statistics.fmean(effective_3a):.6f}",
            "commercial_rate": f"{LINCOLN_NATIONAL_COMMERCIAL_PERCENT / 100.0:.5f}",
            "commercial_tax_bill_1m": "",
            "industrial_rate": f"{LINCOLN_NATIONAL_INDUSTRIAL_PERCENT / 100.0:.5f}",
            "fixtures_exempt": "",
            "metro_proxy": "false",
            "source_table": "3a;4a",
            "as_of": TAX_AS_OF,
            "citation": TAX_CITATION,
        }
    ]
    for postal in sorted(urban):
        rows.append(_tax_row("state_urban", "", "", urban[postal], industrial, proxy=False))
    for postal in sorted(rural):
        rows.append(_tax_row("state_rural", "", "", rural[postal], industrial, proxy=False))
    for state, county_name, place, percent in COUNTY_PLACES:
        fips = by_name.get((state, county_name))
        if fips is None:
            raise SystemExit(f"County not in the crosswalk: {state} {county_name}")
        row = lookup.get((state, place))
        if row is None:
            raise SystemExit(f"Studied place not in Tables 3a-3c: {state} {place}")
        if abs(row.percent - percent) > 0.0005:
            raise SystemExit(f"{place}: table {row.percent}% vs transcribed {percent}%")
        proxy = row.table != "3c" and (state, place) not in NO_METRO_PROXY
        rows.append(
            _tax_row("county", fips, county_cbsa.get(fips, ""), row, industrial, proxy=proxy)
        )
    _write_csv(
        SEED / "property_tax_commercial.csv",
        (
            "level",
            "state",
            "county_fips",
            "cbsa",
            "place",
            "effective_rate",
            "commercial_rate",
            "commercial_tax_bill_1m",
            "industrial_rate",
            "fixtures_exempt",
            "metro_proxy",
            "source_table",
            "as_of",
            "citation",
        ),
        rows,
    )
    print(f"property tax: {len(rows)} rows")


def _fixtures_exempt(row: LincolnRow) -> bool:
    if row.state in FIXTURES_EXEMPT_STATES:
        return True
    return row.table == "3c" and row.state in FIXTURES_EXEMPT_RURAL


def _real_rate(row: LincolnRow) -> float:
    """Tax on land and building per dollar of land and building."""
    if not _fixtures_exempt(row):
        return row.percent / 100.0
    rate = row.bill / 1_000_000.0
    if abs(rate - 1.2 * row.percent / 100.0) > 0.00002:
        raise SystemExit(f"{row.city}: bill {row.bill} is not 1.2 x {row.percent}% of $1 million")
    return rate


def _tax_row(
    level: str,
    fips: str,
    cbsa: str,
    row: LincolnRow,
    industrial: dict[tuple[str, str, str], LincolnRow],
    *,
    proxy: bool,
) -> dict[str, str]:
    partner = industrial[(row.table, row.state, row.city)]
    return {
        "level": level,
        "state": row.state,
        "county_fips": fips,
        "cbsa": cbsa,
        "place": row.city,
        "effective_rate": f"{_real_rate(row):.6f}",
        "commercial_rate": f"{row.percent / 100.0:.5f}",
        "commercial_tax_bill_1m": str(row.bill),
        "industrial_rate": f"{partner.percent / 100.0:.5f}",
        "fixtures_exempt": "true" if _fixtures_exempt(row) else "false",
        "metro_proxy": "true" if proxy else "false",
        "source_table": f"{row.table};{partner.table}",
        "as_of": TAX_AS_OF,
        "citation": TAX_CITATION,
    }


def write_construction_cost(dod_xlsx: Path) -> None:
    """County, CBSA, and state MILCON area cost factors from UFS 3-701-01.

    The workbook lists DoD sites. A county's factor is the lower median of
    its sites' factors (sites in one county almost always share one value).
    A CBSA or state factor is the lower median of its counties' factors, so
    a large installation does not outweigh the rest of the area. The lower
    median keeps every stored value one the DoD published. The DoD scale is
    1.00 at the average of its 96 base cities.
    """
    from dce.data.ingest.bls_oews import oews_area_for_cbsa

    rows = read_xlsx_rows(dod_xlsx.read_bytes(), ACF_SHEET)
    header = [cell.strip() for cell in rows[0]]
    try:
        at = {name: header.index(name) for name in ("Country", "State", "County", "Zip")}
        at["acf"] = header.index("AREA COST FACTOR")
    except ValueError as exc:
        raise SystemExit(f"{ACF_SHEET} header changed: {header}") from exc
    counties = _crosswalk_counties()
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fips, (state, name) in counties.items():
        by_key[(state, _norm_county(name))].append(fips)
    zip_county = _crosswalk_zip_county()
    postal_of = {name.lower(): postal for name, postal in STATE_NAMES.items()}
    sites: dict[str, list[float]] = defaultdict(list)
    skipped = 0
    for row in rows[1:]:
        cells = row + [""] * (len(header) - len(row))
        if cells[at["Country"]].strip() != "United States":
            continue
        postal = postal_of.get(cells[at["State"]].strip().lower())
        try:
            acf = float(cells[at["acf"]])
        except ValueError:
            skipped += 1
            continue
        if postal is None or acf <= 0.0:
            skipped += 1
            continue
        named = by_key.get((postal, _norm_county(cells[at["County"]])), [])
        fips = named[0] if len(named) == 1 else zip_county.get(cells[at["Zip"]].strip()[:5], "")
        if not fips or counties.get(fips, ("", ""))[0] != postal:
            skipped += 1
            continue
        sites[fips].append(acf)
    county_acf = {fips: statistics.median_low(values) for fips, values in sites.items()}

    county_cbsa = _crosswalk_county_cbsa()
    cbsa_names = _crosswalk_cbsa_names()
    by_cbsa: dict[str, list[float]] = defaultdict(list)
    by_state: dict[str, list[float]] = defaultdict(list)
    cbsa_states: dict[str, set[str]] = defaultdict(set)
    divisions: dict[str, set[str]] = defaultdict(set)
    uncovered: set[str] = set()
    for fips, code in county_cbsa.items():
        if not code:
            continue
        codes = {code, oews_area_for_cbsa(code)}
        if fips not in county_acf:
            uncovered |= codes
        if fips not in counties:
            continue
        for key in codes:
            cbsa_states[key].add(counties[fips][0])
            if key != code:
                divisions[key].add(code)
            if fips in county_acf:
                by_cbsa[key].append(county_acf[fips])
    for fips, acf in county_acf.items():
        by_state[counties[fips][0]].append(acf)
    # A CBSA row is only read for a county with no row of its own.
    by_cbsa = {code: values for code, values in by_cbsa.items() if code in uncovered}

    out: list[dict[str, str]] = [
        _acf_row("national", "US", "US", "DoD 96-base-city average", 1.0, 96, full=True)
    ]
    for postal in sorted(by_state):
        values = by_state[postal]
        name = next(k for k, v in STATE_NAMES.items() if v == postal)
        out.append(
            _acf_row("state", postal, postal, name, statistics.median_low(values), len(values))
        )
    for code in sorted(by_cbsa):
        values = by_cbsa[code]
        name = cbsa_names.get(code) or "CBSA with divisions " + ", ".join(sorted(divisions[code]))
        state = "-".join(sorted(cbsa_states[code]))
        out.append(_acf_row("cbsa", code, state, name, statistics.median_low(values), len(values)))
    for fips in sorted(county_acf):
        state, name = counties[fips]
        out.append(_acf_row("county", fips, state, name, county_acf[fips], len(sites[fips])))
    _write_csv(
        SEED / "construction_cost_factor.csv",
        (
            "level",
            "geography_id",
            "state",
            "name",
            "acf",
            "count",
            "as_of",
            "source",
            "citation",
        ),
        out,
    )
    print(
        f"construction cost: {len(county_acf)} counties, {len(by_cbsa)} CBSAs, "
        f"{len(by_state)} states, {skipped} sites skipped"
    )


def _acf_row(
    level: str,
    geography_id: str,
    state: str,
    name: str,
    acf: float,
    count: int,
    *,
    full: bool = False,
) -> dict[str, str]:
    return {
        "level": level,
        "geography_id": geography_id,
        "state": state,
        "name": name,
        "acf": f"{acf:.2f}",
        "count": str(count),
        "as_of": ACF_AS_OF,
        "source": ACF_SOURCE,
        "citation": f"{ACF_CITATION}. {ACF_URL}" if full else ACF_CITATION,
    }


def write_rpp(cache: Path) -> None:
    state_path = _zip_member(cache / "SARPP.zip", "SARPP_STATE_2008_2024.csv")
    metro_path = _zip_member(cache / "MARPP.zip", "MARPP_MSA_2008_2024.csv")
    rows: list[dict[str, str]] = []
    for kind, path, id_of in (
        ("state", state_path, _state_id),
        ("metro", metro_path, _metro_id),
    ):
        grouped = _rpp_groups(path)
        for geo_id, (name, goods, all_items) in sorted(grouped.items()):
            mapped = id_of(geo_id, name)
            if mapped is None:
                continue
            rows.append(
                {
                    "geography_type": "national" if mapped == "US" else kind,
                    "geography_id": mapped,
                    "name": name,
                    "rpp_goods": f"{goods:.3f}",
                    "rpp_all_items": f"{all_items:.3f}",
                    "as_of": BEA_AS_OF,
                    "citation": BEA_CITATION,
                }
            )
    _write_csv(
        SEED / "bea_rpp_2024.csv",
        (
            "geography_type",
            "geography_id",
            "name",
            "rpp_goods",
            "rpp_all_items",
            "as_of",
            "citation",
        ),
        rows,
    )
    print(f"rpp: {len(rows)} rows")


def _rate(
    level: str,
    geo_id: str,
    name: str,
    cents: float,
    demand: str,
    schedule: str,
    as_of: str,
    source: str,
    citation: str,
    *,
    energy_dollars: float | None = None,
) -> dict[str, str]:
    energy = cents / 100.0 if energy_dollars is None else energy_dollars
    return {
        "level": level,
        "geo_id": geo_id,
        "name": name,
        "energy_rate_kwh": f"{energy:.6f}",
        "demand_rate_kw": demand,
        "schedule": schedule,
        "as_of": as_of,
        "source": source,
        "citation": citation,
    }


def _epm_prices(path: Path) -> dict[str, float]:
    rows = read_xlsx_rows(path.read_bytes())
    found: dict[str, float] = {}
    for row in rows:
        if not row:
            continue
        label = row[0].replace("\n", " ").strip()
        if label == "U.S. Total":
            found["US"] = float(row[3])
        postal = STATE_NAMES.get(label)
        if postal is not None:
            found[postal] = float(row[3])
    missing = sorted(set(STATE_NAMES.values()) - set(found))
    if missing or "US" not in found:
        raise SystemExit(f"EPM table is missing {missing or 'US'}")
    return found


_UTILITY_MWH: dict[str, float] = {}


def _utility_prices(path: Path) -> dict[str, tuple[float, str]]:
    """Return utility id -> ($/kWh, name). Fills ``_UTILITY_MWH``."""
    rows = read_xlsx_rows(path.read_bytes())
    revenue: dict[str, float] = defaultdict(float)
    mwh_by_id: dict[str, float] = defaultdict(float)
    names: dict[str, str] = {}
    for row in rows[3:]:
        if len(row) < 14:
            continue
        utility_id = row[1].strip()
        if not utility_id.isdigit():
            continue
        service = row[4].strip().lower()
        names[utility_id] = row[2].strip()
        try:
            rev = float(row[12]) if row[12] else 0.0
            mwh = float(row[13]) if row[13] else 0.0
        except ValueError:
            continue
        # Thousand dollars and MWh. $/kWh = revenue_thousands / mwh.
        revenue[utility_id] += rev
        if service in {"bundled", "delivery"}:
            mwh_by_id[utility_id] += mwh
    prices: dict[str, tuple[float, str]] = {}
    _UTILITY_MWH.clear()
    for utility_id, mwh in mwh_by_id.items():
        if mwh <= 0.0 or revenue[utility_id] <= 0.0:
            continue
        prices[utility_id] = (revenue[utility_id] / mwh, names[utility_id])
        _UTILITY_MWH[utility_id] = mwh
    if PGE_UTILITY_ID not in prices:
        raise SystemExit("EIA-861 sales file has no Pacific Gas & Electric (14328)")
    return prices


def _territory(path: Path) -> dict[tuple[str, str], set[str]]:
    """Return (state, normalized county) -> utility ids."""
    rows = read_xlsx_rows(path.read_bytes())
    out: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows[1:]:
        if len(row) < 6:
            continue
        utility_id = row[1].strip()
        state = row[4].strip()
        county = row[5].strip()
        if not utility_id.isdigit() or len(state) != 2 or county == "":
            continue
        out[(state, _norm_county(county))].add(utility_id)
    return out


def _crosswalk_counties() -> dict[str, tuple[str, str]]:
    """Return county FIPS -> (state, county name)."""
    found: dict[str, tuple[str, str]] = {}
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            found[row["county_fips"]] = (row["state"], row["county_name"])
    return found


def _crosswalk_county_cbsa() -> dict[str, str]:
    """Return county FIPS -> the CBSA or metro division most of its ZIPs use."""
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            votes[row["county_fips"]][row["cbsa"].strip()] += 1
    return {
        fips: min(counter.items(), key=lambda item: (-item[1], item[0]))[0]
        for fips, counter in votes.items()
    }


def _crosswalk_cbsa_names() -> dict[str, str]:
    found: dict[str, str] = {}
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["cbsa"].strip():
                found.setdefault(row["cbsa"].strip(), row["cbsa_name"].strip())
    return found


def _crosswalk_zip_county() -> dict[str, str]:
    """Return ZIP -> the county with the largest address share."""
    best: dict[str, tuple[float, str]] = {}
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                ratio = float(row["tot_ratio"] or 0.0)
            except ValueError:
                ratio = 0.0
            held = best.get(row["zip"])
            if held is None or ratio > held[0]:
                best[row["zip"]] = (ratio, row["county_fips"])
    return {code: fips for code, (_ratio, fips) in best.items()}


def _assign_counties(
    territory: dict[tuple[str, str], set[str]],
    sales: dict[str, tuple[float, str]],
    counties: dict[str, tuple[str, str]],
) -> tuple[dict[str, tuple[str, float]], int, int]:
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for fips, (state, name) in counties.items():
        by_key[(state, _norm_county(name))].append(fips)
    chosen: dict[str, tuple[str, float]] = {}
    unmatched = 0
    ambiguous = 0
    for key, utility_ids in territory.items():
        fips_list = by_key.get(key, [])
        if len(fips_list) != 1:
            if not fips_list:
                unmatched += 1
            else:
                ambiguous += 1
            continue
        ranked = _rank_utilities(utility_ids, sales)
        if ranked is None:
            unmatched += 1
            continue
        chosen[fips_list[0]] = ranked
    return chosen, unmatched, ambiguous


def _rank_utilities(
    utility_ids: set[str], sales: dict[str, tuple[float, str]]
) -> tuple[str, float] | None:
    """Pick the utility with the largest commercial sales.

    ``sales`` values are (dollars per kWh, name). Megawatthours are recovered
    from the module-level cache filled by :func:`_utility_prices`.
    """
    best: tuple[str, float] | None = None
    for utility_id in utility_ids:
        mwh = _UTILITY_MWH.get(utility_id)
        if mwh is None or utility_id not in sales:
            continue
        if best is None or mwh > best[1] or (mwh == best[1] and int(utility_id) < int(best[0])):
            best = (utility_id, mwh)
    return best


def _norm_county(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace(".", "").replace("'", "")
    text = text.replace("saint ", "st ").replace("ste ", "st ")
    for suffix in (
        " census area",
        " municipality",
        " city and borough",
        " borough",
        " parish",
        " county",
        " city",
    ):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return re.sub(r"[^a-z0-9]", "", text)


def _rpp_groups(text: str) -> dict[str, tuple[str, float, float]]:
    """Return geo id -> (name, goods, all items) for 2024."""
    goods: dict[str, tuple[str, float]] = {}
    all_items: dict[str, tuple[str, float]] = {}
    reader = csv.reader(text.splitlines())
    header = next(reader)
    try:
        year_at = header.index("2024")
    except ValueError as exc:
        raise SystemExit("BEA file has no 2024 column") from exc
    for row in reader:
        if len(row) <= year_at:
            continue
        geo_id = row[0].strip().strip('"')
        if not geo_id.isdigit():
            continue
        name = row[1].strip().strip('"')
        description = row[6].strip()
        try:
            value = float(row[year_at])
        except ValueError:
            continue
        if description == "RPPs: Goods":
            goods[geo_id] = (name, value)
        elif description == "RPPs: All items":
            all_items[geo_id] = (name, value)
    grouped: dict[str, tuple[str, float, float]] = {}
    for geo_id, (name, goods_value) in goods.items():
        if geo_id not in all_items:
            continue
        grouped[geo_id] = (name, goods_value, all_items[geo_id][1])
    return grouped


def _state_id(geo_id: str, name: str) -> str | None:
    if geo_id == "00000" or name == "United States":
        return "US"
    return FIPS_TO_POSTAL.get(geo_id)


def _metro_id(geo_id: str, name: str) -> str | None:
    if geo_id == "00000":
        return None  # national row comes from the state file
    if not geo_id.isdigit() or len(geo_id) != 5:
        return None
    if "Nonmetropolitan" in name:
        return None
    return geo_id


def _zip_member(path: Path, member: str) -> str:
    with zipfile.ZipFile(path) as archive:
        return archive.read(member).decode("utf-8-sig")


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
