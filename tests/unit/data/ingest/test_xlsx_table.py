"""Minimal xlsx reader. No network."""

from __future__ import annotations

import io
import zipfile

from dce.data.ingest.xlsx_table import XlsxTableError, read_xlsx_rows

_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def test_reads_shared_strings_numbers_and_sparse_cells() -> None:
    shared = f"""<?xml version="1.0"?>
<sst xmlns="{_NS}">
  <si><t>ZIP</t></si>
  <si><t>Name</t></si>
  <si><t>00501</t></si>
</sst>
"""
    sheet = f"""<?xml version="1.0"?>
<worksheet xmlns="{_NS}">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>2</v></c>
      <c r="C2"><v>12</v></c>
    </row>
  </sheetData>
</worksheet>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    rows = read_xlsx_rows(buffer.getvalue())
    assert rows == [["ZIP", "Name"], ["00501", "", "12"]]


def test_reads_a_named_worksheet() -> None:
    workbook = f"""<?xml version="1.0"?>
<workbook xmlns="{_NS}"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Notes" sheetId="1" r:id="rId1"/>
    <sheet name="Table 4-1 CONUS" sheetId="2" r:id="rId2"/>
  </sheets>
</workbook>
"""
    rels = """<?xml version="1.0"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="worksheet" Target="/xl/worksheets/sheet7.xml"/>
</Relationships>
"""

    def sheet(text: str) -> str:
        return (
            f'<?xml version="1.0"?><worksheet xmlns="{_NS}"><sheetData>'
            f'<row r="1"><c r="A1" t="inlineStr"><is><t>{text}</t></is></c></row>'
            "</sheetData></worksheet>"
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet("notes"))
        archive.writestr("xl/worksheets/sheet7.xml", sheet("acf"))
    payload = buffer.getvalue()
    assert read_xlsx_rows(payload) == [["notes"]]
    assert read_xlsx_rows(payload, "Table 4-1 CONUS") == [["acf"]]
    try:
        read_xlsx_rows(payload, "Missing")
    except XlsxTableError as exc:
        assert "Missing" in str(exc)
    else:
        raise AssertionError("a missing sheet must raise")
