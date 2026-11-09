"""ZIP crosswalk assembly from small public-file fixtures. No network."""

from __future__ import annotations

from dce.data.ingest.zip_geography import (
    CountyCbsa,
    assemble_zip_crosswalk,
    division_parents,
    parse_cbsa_delineation,
    parse_hrsa_zip_zcta,
    parse_zcta_county_relationship,
)

_RELATIONSHIP = """\
GEOID_ZCTA5_20|GEOID_COUNTY_20|NAMELSAD_COUNTY_20|AREALAND_PART
|06081|San Mateo County|100
94402|06081|San Mateo County|80
94402|06001|Alameda County|20
10001|36061|New York County|50
00601|72001|Adjuntas Municipio|10
11742|36103|Suffolk County|10
"""

_DELINEATION = [
    ["OMB Bulletin"],
    [
        "CBSA Code",
        "Metropolitan Division Code",
        "CBSA Title",
        "Metropolitan Division Title",
        "Metropolitan/Micropolitan Statistical Area",
        "FIPS State Code",
        "FIPS County Code",
    ],
    [
        "41860",
        "41884",
        "San Francisco-Oakland-Fremont, CA",
        "San Francisco-San Mateo-Redwood City, CA",
        "Metropolitan Statistical Area",
        "6",
        "81",
    ],
    [
        "41860",
        "36084",
        "San Francisco-Oakland-Fremont, CA",
        "Oakland-Fremont-Berkeley, CA",
        "Metropolitan Statistical Area",
        "06",
        "001",
    ],
    [
        "35620",
        "35614",
        "New York-Newark-Jersey City, NY-NJ",
        "New York-Jersey City-White Plains, NY-NJ",
        "Metropolitan Statistical Area",
        "36",
        "061",
    ],
]


def test_94402_keeps_the_san_mateo_division_and_land_share() -> None:
    parts = parse_zcta_county_relationship(_RELATIONSHIP)
    counties = {row.county_fips: row for row in parse_cbsa_delineation(_DELINEATION)}
    hrsa = parse_hrsa_zip_zcta(
        [
            ["ZIP_CODE", "STATE", "ZCTA", "ZIP_JOIN_TYPE"],
            ["501", "NY", "11742", "Spatial join to ZCTA"],
            ["99999", "CA", "No ZCTA", ""],
        ]
    )
    rows = assemble_zip_crosswalk(parts, counties, hrsa)
    mateo = next(row for row in rows if row.zip_code == "94402" and row.county_fips == "06081")
    alameda = next(row for row in rows if row.zip_code == "94402" and row.county_fips == "06001")
    assert mateo.cbsa == "41884"
    assert mateo.state == "CA"
    assert mateo.tot_ratio == 0.8
    assert alameda.cbsa == "36084"
    assert alameda.tot_ratio == 0.2
    holtsville = next(row for row in rows if row.zip_code == "00501")
    assert holtsville.zcta == "11742"
    assert holtsville.state == "NY"
    assert holtsville.tot_ratio == 1
    assert all(row.zip_code != "99999" for row in rows)
    puerto = next(row for row in rows if row.zip_code == "00601")
    assert puerto.state == "PR"
    assert puerto.cbsa == ""
    parents = division_parents(tuple(counties.values()))
    assert parents["41884"] == "41860"
    assert parents["35614"] == "35620"
    assert isinstance(next(iter(counties.values())), CountyCbsa)
