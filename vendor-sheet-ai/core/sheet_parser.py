from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ParsedSheet:
    headers: list[str]
    rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None


def parse_sheet(file_path: str | Path) -> ParsedSheet:
    path = Path(file_path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))

    if not rows:
        return ParsedSheet(headers=[], rows=[])

    raw_headers = rows[0]
    headers = [header.strip() for header in raw_headers if header and header.strip()]

    data_rows: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not any(cell and str(cell).strip() for cell in row):
            continue
        record: dict[str, Any] = {}
        for index, header in enumerate(headers):
            value = row[index] if index < len(row) else ""
            record[header] = value.strip() if isinstance(value, str) else value
        data_rows.append(record)

    return ParsedSheet(headers=headers, rows=data_rows, metadata={"source_file": str(path)})


def _fill_count(row: list[str]) -> int:
    return sum(1 for cell in row if cell and cell.strip())


def _find_header_row(rows: list[list[str]]) -> int:
    """Locate the real header row when a sheet has leading junk rows
    (titles, blank rows, filter labels) before the actual column headers."""
    scan_limit = min(10, len(rows))
    if scan_limit == 0:
        return 0

    fills = [_fill_count(rows[i]) for i in range(scan_limit)]
    header_row = max(range(scan_limit), key=lambda i: fills[i])
    return header_row


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    deduped: list[str] = []
    for header in headers:
        seen[header] = seen.get(header, 0) + 1
        deduped.append(header if seen[header] == 1 else f"{header} ({seen[header]})")
    return deduped


def _merge_header_rows(primary: list[str], secondary: list[str]) -> list[str]:
    merged: list[str] = []
    last_primary = ""
    width = max(len(primary), len(secondary))

    for index in range(width):
        if index < len(primary):
            top = primary[index].strip()
        else:
            top = ""

        if index < len(secondary):
            sub = secondary[index].strip()
        else:
            sub = ""

        if top:
            last_primary = top
        else:
            top = last_primary

        if sub and sub != top:
            merged.append(f"{top} - {sub}".strip(" -"))
        else:
            merged.append(top)

    return merged


def parse_sheet_text(csv_text: str, source_name: str = "google-sheet") -> ParsedSheet:
    """Parse CSV text from a Google Sheets export.

    Handles two messy real-world layouts on top of the plain single-header case:
    - leading junk rows (titles, blank rows, filter labels) before the real header
    - merged two-row headers (e.g. "Inner box(CM)" spanning L/W/H sub-columns)
    """
    rows = list(csv.reader(csv_text.splitlines()))
    if not rows:
        return ParsedSheet(headers=[], rows=[])

    header_row = _find_header_row(rows)
    header_fill = _fill_count(rows[header_row])
    prev_fill = _fill_count(rows[header_row - 1]) if header_row > 0 else 0

    is_two_row_header = header_row > 0 and header_fill > 0 and 0.2 * header_fill <= prev_fill <= 0.9 * header_fill

    if is_two_row_header:
        raw_headers = _merge_header_rows(rows[header_row - 1], rows[header_row])
        data_start = header_row + 1
    else:
        raw_headers = [cell.strip() for cell in rows[header_row]]
        data_start = header_row + 1

    header_indexes = [i for i, header in enumerate(raw_headers) if header]
    headers = _dedupe_headers([raw_headers[i] for i in header_indexes])

    data_rows: list[dict[str, Any]] = []
    row_numbers: list[int] = []
    for offset, row in enumerate(rows[data_start:]):
        if not any(cell and str(cell).strip() for cell in row):
            continue
        record: dict[str, Any] = {}
        for header, index in zip(headers, header_indexes):
            value = row[index] if index < len(row) else ""
            value = value.strip() if isinstance(value, str) else value
            if value:
                record[header] = value
        if record:
            data_rows.append(record)
            row_numbers.append(data_start + offset)

    return ParsedSheet(
        headers=headers,
        rows=data_rows,
        metadata={"source_file": source_name, "row_numbers": row_numbers},
    )
