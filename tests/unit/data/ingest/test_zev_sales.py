"""CEC New ZEV Sales parsing and the non-California fallback. No network."""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

import pytest

from dce.data.ingest.zev_sales import (
    ZevSalesError,
    ZipDemandProfile,
    allocate_state_tesla_volume,
    fetch_zev_sales,
    newest_zev_workbook_url,
    parse_zev_workbook,
    resolve_zip_tesla_deliveries,
)


def test_workbook_sums_models_and_allocates_tesla_by_county_share() -> None:
    batch = parse_zev_workbook(
        _workbook(), source_url="https://www.energy.ca.gov/filebrowser/download/1"
    )
    assert batch.as_of == "2025-03-31"
    tesla = next(
        row
        for row in batch.county_sales
        if row.county == "San Mateo" and row.make == "Tesla" and row.fuel_type == "Electric"
    )
    assert tesla.vehicles == 100  # Model Y 60 + Model 3 40
    allocated = resolve_zip_tesla_deliveries(
        "CA",
        zip_sales=batch.zip_sales,
        county_sales=batch.county_sales,
        counties=("San Mateo",),
        year=2025,
    )
    # San Mateo Electric is 200, of which Tesla is 100, so the share is 0.5.
    assert allocated["94402"] == pytest.approx(5.0)
    assert allocated["94401"] == pytest.approx(15.0)
    assert "94501" not in allocated  # PHEV only, not battery-electric


def test_catalog_picks_the_newest_workbook_on_energy_ca_gov() -> None:
    html = """
    <a href="/filebrowser/download/1?fid=1">New_ZEV_Sales_Last_updated_04-28-2025_ada.xlsx</a>
    <a href="/filebrowser/download/10036?fid=10036#block-title">New_ZEV_Sales_Last_updated_10-13-2026_ada.xlsx</a>
    """
    url = newest_zev_workbook_url(html)
    assert url == "https://www.energy.ca.gov/filebrowser/download/10036?fid=10036"
    assert "#" not in url


def test_fetch_stays_on_energy_ca_gov(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_bytes(url: str, **_kwargs: object) -> bytes:
        seen.append(url)
        if url.endswith("zev-and-infrastructure-stats-data"):
            return (
                b'<a href="/filebrowser/download/9?fid=9">'
                b"New_ZEV_Sales_Last_updated_10-13-2026_ada.xlsx</a>"
            )
        return _workbook()

    monkeypatch.setattr("dce.data.ingest.zev_sales.request_bytes", fake_bytes)
    batch = fetch_zev_sales()
    assert batch.as_of == "2025-03-31"
    assert all(url.startswith("https://www.energy.ca.gov/") for url in seen)
    assert seen[0] == "https://www.energy.ca.gov/files/zev-and-infrastructure-stats-data"


def test_outside_california_allocates_by_households_income_and_ev_share() -> None:
    profiles = (
        ZipDemandProfile("10001", 100, 80_000, 30, 1000),
        ZipDemandProfile("10002", 100, 160_000, 30, 1000),
        ZipDemandProfile("10003", None, None, None, None),
    )
    allocated = resolve_zip_tesla_deliveries(
        "NY",
        state_tesla_volume=1000,
        profiles=profiles,
    )
    richer = 100 * (2.0**0.3)
    assert "10003" not in allocated
    assert allocated["10001"] == pytest.approx(1000 * 100 / (100 + richer))
    assert allocated["10002"] == pytest.approx(1000 * richer / (100 + richer))
    assert sum(allocated.values()) == pytest.approx(1000)


def test_fallback_rejects_a_zip_whose_ev_stock_exceeds_light_duty() -> None:
    with pytest.raises(ZevSalesError, match="ev_stock"):
        allocate_state_tesla_volume(
            100,
            (ZipDemandProfile("10001", 10, 50_000, 20, 10),),
        )
    with pytest.raises(ZevSalesError, match="Outside California"):
        resolve_zip_tesla_deliveries("TX")


def _workbook() -> bytes:
    sheets = {
        "County": [
            ["Data Year", "Quarter", "COUNTY", "FUEL_TYPE", "MAKE", "MODEL", "Number of Vehicles"],
            ["2025", "1", "San Mateo", "Electric", "Tesla", "Model Y", "60"],
            ["2025", "1", "San Mateo", "Electric", "Tesla", "Model 3", "40"],
            ["2025", "1", "San Mateo", "Electric", "Ford", "Mach-E", "100"],
            ["2025", "1", "Alameda", "Electric", "Tesla", "Model Y", "50"],
        ],
        "ZIP": [
            ["Data_Year", "Quarter", "ZIP", "FUEL_TYPE", "Number of Vehicles"],
            ["2025", "1", "94402", "Electric", "10"],
            ["2025", "1", "94401", "Electric", "30"],
            ["2025", "1", "94501", "PHEV", "5"],
        ],
    }
    strings: list[str] = []
    index: dict[str, int] = {}

    def sid(value: str) -> int:
        if value not in index:
            index[value] = len(strings)
            strings.append(value)
        return index[value]

    sheet_xml: dict[str, str] = {}
    for name, rows in sheets.items():
        body: list[str] = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, value in enumerate(row):
                column = chr(ord("A") + c)
                cells.append(f'<c r="{column}{r}" t="s"><v>{sid(value)}</v></c>')
            body.append(f'<row r="{r}">{"".join(cells)}</row>')
        sheet_xml[name] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f"<sheetData>{''.join(body)}</sheetData></worksheet>"
        )
    shared = "".join(f"<si><t>{escape(value)}</t></si>" for value in strings)
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">{shared}</sst>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="County" sheetId="1" r:id="rId1"/>'
        '<sheet name="ZIP" sheetId="2" r:id="rId2"/>'
        "</sheets></workbook>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    package = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        "</Types>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml["County"])
        archive.writestr("xl/worksheets/sheet2.xml", sheet_xml["ZIP"])
    return buffer.getvalue()
