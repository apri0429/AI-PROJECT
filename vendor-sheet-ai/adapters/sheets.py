from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from config import settings

_ID_PATTERN = re.compile(r"/d/([a-zA-Z0-9_-]+)")
_GID_PATTERN = re.compile(r"[?&#]gid=([0-9]+)")


class SheetFetchError(RuntimeError):
    pass


def parse_sheet_url(url_or_id: str) -> tuple[str, str | None]:
    match = _ID_PATTERN.search(url_or_id)
    sheet_id = match.group(1) if match else url_or_id.strip()

    gid_match = _GID_PATTERN.search(url_or_id)
    gid = gid_match.group(1) if gid_match else None

    if not sheet_id:
        raise SheetFetchError("Could not find a spreadsheet ID in the given URL")

    return sheet_id, gid


def fetch_sheet_csv(sheet_id: str, gid: str | None = None) -> str:
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    if gid:
        export_url += f"&gid={gid}"

    request = urllib.request.Request(export_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise SheetFetchError(f"Google Sheets returned status {response.status}")
            return response.read().decode("utf-8-sig")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SheetFetchError(
                "Cannot access this sheet. Make sure it's shared as "
                "\"Anyone with the link can view\"."
            ) from exc
        raise SheetFetchError(f"Failed to fetch sheet: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SheetFetchError(f"Failed to reach Google Sheets: {exc.reason}") from exc


def _sheets_api_get(path: str, params: dict[str, str]) -> dict:
    if not settings.google_sheets_api_key:
        raise SheetFetchError("GOOGLE_SHEETS_API_KEY is not set")

    query = urllib.parse.urlencode({**params, "key": settings.google_sheets_api_key})
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{path}?{query}"
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise SheetFetchError(f"Google Sheets API error: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SheetFetchError(f"Failed to reach Google Sheets API: {exc.reason}") from exc


def column_letter(index: int) -> str:
    """0-based column index -> spreadsheet column letters (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def fetch_sheet_tab_title(sheet_id: str, gid: str | None) -> str:
    data = _sheets_api_get(sheet_id, {"fields": "sheets.properties"})
    target_gid = int(gid) if gid else 0
    for sheet in data.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("sheetId") == target_gid:
            return props.get("title", "")
    raise SheetFetchError(f"Could not find a tab with gid {gid} in this spreadsheet")


def fetch_chip_links(
    sheet_id: str, tab_title: str, column_index: int, start_row: int, end_row: int
) -> dict[int, str]:
    """Return {raw_row_index (0-based, matching csv rows) -> linked URL} for
    smart-chip links found in the given column, over rows [start_row, end_row)."""
    col = column_letter(column_index)
    a1_range = f"'{tab_title}'!{col}{start_row + 1}:{col}{end_row}"
    data = _sheets_api_get(
        sheet_id,
        {
            "ranges": a1_range,
            "fields": "sheets.data.rowData.values(chipRuns,hyperlink)",
        },
    )

    links: dict[int, str] = {}
    try:
        row_data = data["sheets"][0]["data"][0].get("rowData", [])
    except (KeyError, IndexError):
        return links

    for offset, row in enumerate(row_data):
        values = row.get("values", [])
        if not values:
            continue
        cell = values[0]
        uri = cell.get("hyperlink")
        if not uri:
            for chip_run in cell.get("chipRuns", []):
                uri = chip_run.get("chip", {}).get("richLinkProperties", {}).get("uri")
                if uri:
                    break
        if uri:
            links[start_row + offset] = uri

    return links


def fetch_sheet_detail_text(url: str, max_chars: int = 4000) -> str:
    """Fetch a linked Google Sheet (e.g. a per-product detail sheet) and return
    its content as a compact, readable text block for use as extra AI context."""
    sheet_id, gid = parse_sheet_url(url)
    csv_text = fetch_sheet_csv(sheet_id, gid)

    lines = []
    for row in csv_text.splitlines():
        if not row.strip():
            continue
        line = row.replace(",", ": ", 1)
        if line.strip().lower().endswith("false"):
            continue
        lines.append(line)
        if sum(len(l) for l in lines) > max_chars:
            break

    text = "\n".join(lines)
    return text[:max_chars] if text else "(detail sheet is empty)"
