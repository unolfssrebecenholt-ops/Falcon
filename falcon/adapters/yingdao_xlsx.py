from pathlib import Path
from typing import List
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET

from ..models import RawItem


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class YingdaoXlsxAdapter:
    def load(
        self,
        path: Path,
        keyword: str,
        platform: str = "xiaohongshu",
        source_type: str = "post",
    ) -> List[RawItem]:
        rows = _read_first_sheet_rows(Path(path))
        items = []
        for row in rows:
            if _is_header_row(row):
                continue
            title = _cell(row, 0)
            url = _cell(row, 1)
            if not title or not url:
                continue
            items.append(
                RawItem(
                    platform=platform,
                    keyword=keyword,
                    source_type=source_type,
                    title=title,
                    content=title,
                    url=url,
                    published_at="",
                )
            )
        return items


def _read_first_sheet_rows(path: Path) -> List[List[str]]:
    with ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_name = _first_sheet_name(archive)
        root = ET.fromstring(archive.read(sheet_name))

    rows = []
    for row in root.findall(".//a:row", NS):
        values = []
        for cell in row.findall("a:c", NS):
            index = _column_index(cell.attrib.get("r", ""))
            while len(values) <= index:
                values.append("")
            values[index] = _cell_text(cell, shared_strings)
        rows.append(values)
    return rows


def _read_shared_strings(archive: ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("a:si", NS):
        strings.append("".join(text.text or "" for text in item.findall(".//a:t", NS)))
    return strings


def _first_sheet_name(archive: ZipFile) -> str:
    names = archive.namelist()
    for name in names:
        if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name):
            return name
    raise ValueError("No worksheet found in xlsx file")


def _cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//a:t", NS)).strip()

    value = cell.find("a:v", NS)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell_type == "s":
        return shared_strings[int(raw)].strip()
    return raw.strip()


def _column_index(cell_ref: str) -> int:
    letters = "".join(char for char in cell_ref if char.isalpha())
    if not letters:
        return 0
    index = 0
    for char in letters:
        index = index * 26 + (ord(char.upper()) - ord("A") + 1)
    return index - 1


def _is_header_row(row: List[str]) -> bool:
    first = _cell(row, 0).lower()
    second = _cell(row, 1).lower()
    return (first, second) in {("a", "b"), ("title", "url"), ("标题", "链接")}


def _cell(row: List[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()
