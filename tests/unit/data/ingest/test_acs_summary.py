"""ACS table-based summary files. No network."""

from __future__ import annotations

from dce.data.ingest.census_acs import (
    GROSS_RENT_VARIABLE,
    POPULATION_VARIABLE,
    zcta_acs_from_summary_files,
)

_POPULATION = """\
GEO_ID|B01003_E001
860Z200US94402|25475
860Z200US00601|17113
"""

_RENT = """\
GEO_ID|B25064_E001|B25064_M001
860Z200US94402|3501|-333333333
860Z200US00601|-666666666|100
"""


def test_summary_files_keep_estimates_and_drop_sentinels() -> None:
    rows = {
        row.zcta: row
        for row in zcta_acs_from_summary_files(
            2024,
            {POPULATION_VARIABLE: _POPULATION, GROSS_RENT_VARIABLE: _RENT},
        )
    }
    assert rows["94402"].population == 25475
    assert rows["94402"].median_gross_rent == 3501
    assert rows["00601"].population == 17113
    assert rows["00601"].median_gross_rent is None
    assert rows["94402"].households is None
