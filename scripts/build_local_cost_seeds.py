"""Build the committed electricity, property-tax, and price-index seeds.

Runtime ``estimate`` reads the CSVs this script writes. It does not download
them. Re-run the script only when refreshing the public files in ``--cache``.

Inputs, all public:

- EIA Electric Power Monthly table 5.6.A (commercial cents/kWh by state).
- EIA-861 2024 sales to ultimate customers and service territories.
- BEA Regional Price Parities, 2024 (SARPP and MARPP).
- Lincoln Institute / Minnesota Center for Fiscal Excellence, 50-State
  Property Tax Comparison Study, taxes paid in 2024. The commercial rates
  below are the $1 million property plus $200,000 of fixtures, transcribed
  from Appendix Tables 3a, 3b, and 3c. The PDF is not stored in git.

PG&E Schedule B-10 is applied later by the resolver for utility 14328.
This script still stores that utility's EIA-861 average so the ladder has
both rungs.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict
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
    "Property Tax Comparison Study, taxes paid in 2024, $1 million commercial "
    "property plus $200,000 fixtures. "
    "https://www.lincolninst.edu/publications/other/50-state-property-tax-comparison-study-2024/"
)

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

# Commercial effective rates, percent, $1 million building + $200,000 fixtures.
# state_urban is the largest city, except Illinois (Aurora, not Chicago) and
# New York (Buffalo, not New York City), matching the study's note that those
# two cities are not the rest of the state. state_rural is Appendix Table 3c.
# District of Columbia has no rural analogue; the rural rung repeats the city.
STATE_URBAN_PERCENT = {
    "AL": 1.442,
    "AK": 1.426,
    "AZ": 1.620,
    "AR": 1.366,
    "CA": 1.200,
    "CO": 2.106,
    "CT": 2.309,
    "DE": 0.846,
    "DC": 1.129,
    "FL": 1.635,
    "GA": 1.505,
    "HI": 1.052,
    "ID": 0.751,
    "IL": 2.608,
    "IN": 2.550,
    "IA": 2.695,
    "KS": 2.387,
    "KY": 1.283,
    "LA": 1.714,
    "ME": 1.376,
    "MD": 2.823,
    "MA": 2.106,
    "MI": 3.996,
    "MN": 2.355,
    "MS": 2.745,
    "MO": 2.750,
    "MT": 0.786,
    "NE": 1.838,
    "NV": 1.131,
    "NH": 1.232,
    "NJ": 1.770,
    "NM": 1.685,
    "NY": 1.640,
    "NC": 0.711,
    "ND": 1.121,
    "OH": 1.909,
    "OK": 1.420,
    "OR": 2.593,
    "PA": 1.977,
    "RI": 3.070,
    "SC": 1.937,
    "SD": 1.187,
    "TN": 0.937,
    "TX": 1.997,
    "UT": 0.928,
    "VT": 2.261,
    "VA": 0.873,
    "WA": 0.785,
    "WV": 1.856,
    "WI": 1.959,
    "WY": 0.599,
}
STATE_RURAL_PERCENT = {
    "AL": 0.795,
    "AK": 1.043,
    "AZ": 0.811,
    "AR": 0.819,
    "CA": 1.065,
    "CO": 2.414,
    "CT": 0.983,
    "DE": 0.362,
    "DC": 1.129,
    "FL": 2.006,
    "GA": 1.672,
    "HI": 0.675,
    "ID": 0.668,
    "IL": 2.525,
    "IN": 2.838,
    "IA": 2.827,
    "KS": 3.808,
    "KY": 1.168,
    "LA": 1.314,
    "ME": 1.958,
    "MD": 2.023,
    "MA": 1.938,
    "MI": 2.711,
    "MN": 2.255,
    "MS": 2.064,
    "MO": 2.444,
    "MT": 0.957,
    "NE": 2.033,
    "NV": 1.257,
    "NH": 1.592,
    "NJ": 1.981,
    "NM": 1.088,
    "NY": 2.383,
    "NC": 0.913,
    "ND": 1.370,
    "OH": 1.425,
    "OK": 1.007,
    "OR": 1.136,
    "PA": 1.870,
    "RI": 1.404,
    "SC": 2.985,
    "SD": 1.433,
    "TN": 0.939,
    "TX": 2.066,
    "UT": 0.964,
    "VT": 2.372,
    "VA": 0.868,
    "WA": 0.862,
    "WV": 1.171,
    "WI": 1.723,
    "WY": 0.743,
}
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
NATIONAL_COMMERCIAL_PERCENT = 1.755  # study average, 53 largest cities, $1 million


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/dce-public"))
    args = parser.parse_args()
    cache: Path = args.cache
    write_electricity(cache)
    write_property_tax()
    write_rpp(cache)
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


def write_property_tax() -> None:
    counties = _crosswalk_counties()
    by_name: dict[tuple[str, str], str] = {}
    for fips, (state, name) in counties.items():
        by_name[(state, name)] = fips
    rows: list[dict[str, str]] = [
        _tax("national", "US", "", "53-city average", NATIONAL_COMMERCIAL_PERCENT)
    ]
    urban_place = {
        state: place
        for state, _county, place, percent in COUNTY_PLACES
        if STATE_URBAN_PERCENT[state] == percent
    }
    rural_place = {
        state: place
        for state, _county, place, percent in COUNTY_PLACES
        if STATE_RURAL_PERCENT[state] == percent
    }
    for postal, percent in sorted(STATE_URBAN_PERCENT.items()):
        rows.append(_tax("state_urban", postal, "", urban_place[postal], percent))
    for postal, percent in sorted(STATE_RURAL_PERCENT.items()):
        rows.append(_tax("state_rural", postal, "", rural_place[postal], percent))
    for state, county_name, place, percent in COUNTY_PLACES:
        fips = by_name.get((state, county_name))
        if fips is None:
            raise SystemExit(f"County not in the crosswalk: {state} {county_name}")
        rows.append(_tax("county", state, fips, place, percent))
    _write_csv(
        SEED / "property_tax_commercial.csv",
        ("level", "state", "county_fips", "place", "effective_rate", "as_of", "citation"),
        rows,
    )
    print(f"property tax: {len(rows)} rows")


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


def _tax(level: str, state: str, fips: str, place: str, percent: float) -> dict[str, str]:
    return {
        "level": level,
        "state": state,
        "county_fips": fips,
        "place": place,
        "effective_rate": f"{percent / 100.0:.5f}",
        "as_of": TAX_AS_OF,
        "citation": TAX_CITATION,
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
