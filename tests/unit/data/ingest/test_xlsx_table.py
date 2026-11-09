"""Minimal xlsx reader. No network."""

from __future__ import annotations

import io
import zipfile

from dce.data.ingest.xlsx_table import read_xlsx_rows

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
