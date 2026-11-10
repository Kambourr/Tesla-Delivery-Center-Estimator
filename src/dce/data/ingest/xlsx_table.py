"""Read the first worksheet of an Office Open XML workbook.

The Census delineation file and the HRSA ZIP-to-ZCTA workbook are ``.xlsx``.
This reader uses the standard library so ingest does not add a spreadsheet
package. It does not open SQLite and it does not use the network.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

from dce.data.ingest.http import IngestError

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class XlsxTableError(IngestError):
    """A workbook could not be read as a table of strings."""


def read_xlsx_rows(payload: bytes, sheet_name: str | None = None) -> list[list[str]]:
    """Return every row of one worksheet. Missing cells are ``""``.

    ``sheet_name`` picks a worksheet by its tab name. ``None`` reads the
    first worksheet part, ``xl/worksheets/sheet1.xml``. Numbers stay as the
    text Excel stored. Shared strings are resolved.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise XlsxTableError("Workbook is not a ZIP (xlsx) file.") from exc
    shared = _shared_strings(archive)
    part = "xl/worksheets/sheet1.xml" if sheet_name is None else _sheet_part(archive, sheet_name)
    try:
        sheet = archive.read(part)
    except KeyError as exc:
        raise XlsxTableError(f"Workbook has no {part}.") from exc
    try:
        root = ElementTree.fromstring(sheet)
    except ElementTree.ParseError as exc:
        raise XlsxTableError("Workbook sheet XML is not well formed.") from exc
    rows: list[list[str]] = []
    for row in root.findall(f"{_NS}sheetData/{_NS}row"):
        values: dict[int, str] = {}
        for cell in row.findall(f"{_NS}c"):
            ref = cell.attrib.get("r", "")
            column = _column_index(ref)
            if column is None:
                continue
            values[column] = _cell_text(cell, shared)
        if not values:
            continue
        width = max(values) + 1
        rows.append([values.get(index, "") for index in range(width)])
    if not rows:
        raise XlsxTableError("Workbook sheet has no rows.")
    return rows


def _sheet_part(archive: zipfile.ZipFile, sheet_name: str) -> str:
    """Return the archive path of the worksheet whose tab is ``sheet_name``."""
    try:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ElementTree.ParseError) as exc:
        raise XlsxTableError("Workbook has no readable sheet index.") from exc
    targets = {
        rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
        for rel in rels.findall(f"{_PKG_REL_NS}Relationship")
    }
    for sheet in workbook.iter(f"{_NS}sheet"):
        if sheet.attrib.get("name") != sheet_name:
            continue
        target = targets.get(sheet.attrib.get(f"{_REL_NS}id", ""), "")
        if not target:
            break
        target = target.lstrip("/")
        return target if target.startswith("xl/") else f"xl/{target}"
    raise XlsxTableError(f"Workbook has no worksheet named {sheet_name!r}.")


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except ElementTree.ParseError as exc:
        raise XlsxTableError("Workbook shared strings are not well formed.") from exc
    strings: list[str] = []
    for item in root.findall(f"{_NS}si"):
        strings.append("".join(node.text or "" for node in item.iter(f"{_NS}t")))
    return strings


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        inline = cell.find(f"{_NS}is")
        if inline is None:
            return ""
        return "".join(node.text or "" for node in inline.iter(f"{_NS}t"))
    value = cell.find(f"{_NS}v")
    if value is None or value.text is None:
        return ""
    if kind == "s":
        try:
            return shared[int(value.text)]
        except (ValueError, IndexError) as exc:
            raise XlsxTableError("Workbook shared-string index is out of range.") from exc
    return value.text


def _column_index(ref: str) -> int | None:
    number = 0
    seen = False
    for char in ref:
        if not char.isalpha():
            break
        seen = True
        number = number * 26 + (ord(char.upper()) - 64)
    if not seen:
        return None
    return number - 1
