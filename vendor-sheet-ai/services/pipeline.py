from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import settings
from core.dieline import calculate_dieline
from core.prompts import build_summary_prompt
from core.sheet_parser import parse_sheet, parse_sheet_text
from core.validator import validate_rows
from adapters.llm import generate_summary
from adapters.docs import write_doc
from adapters.sheets import (
    SheetFetchError,
    fetch_chip_links,
    fetch_sheet_csv,
    fetch_sheet_detail_text,
    fetch_sheet_tab_title,
    parse_sheet_url,
)
from adapters.tracker import update_master_sheet
from models import PipelineResult
from storage.state import StateStore

logger = logging.getLogger(__name__)

_DETAIL_LINK_HEADER_HINT = "link detail"
_MARKETING_PICTURE_HEADER_HINT = "link marketing picture"


def process_file(file_path: str | Path) -> PipelineResult:
    parsed_sheet = parse_sheet(file_path)
    issues = validate_rows(parsed_sheet.rows)

    normalized_rows: list[dict[str, Any]] = []
    for row in parsed_sheet.rows:
        dieline = calculate_dieline(row.get("width"), row.get("height"))
        prompt = build_summary_prompt(row)
        summary = generate_summary(prompt)
        write_doc(row.get("product_name", "untitled"), summary)
        update_master_sheet(row)
        normalized_rows.append({**row, "dieline": dieline, "llm_summary": summary})

    file_name = Path(file_path).name
    store = StateStore()
    store.mark_processed(file_name)
    store.save_rows(file_name, normalized_rows)
    return PipelineResult(file_name=file_name, normalized_rows=normalized_rows, issues=issues)


_TITLE_FIELD_CANDIDATES = (
    "product_name", "product name", "parent name", "nama produk",
    "item name", "product", "nama barang",
)


def _pick_title_field(headers: list[str]) -> str | None:
    if not headers:
        return None
    lowered = {h.lower(): h for h in headers}
    for candidate in _TITLE_FIELD_CANDIDATES:
        if candidate in lowered:
            return lowered[candidate]
    return headers[0]


_IGNORED_DATA_FIELDS = {"no"}  # a running row number, present even on fully blank spacer rows


def _row_has_data(row: dict[str, Any], primary_field: str | None) -> bool:
    """True if any field besides the title (and the row-number column) has a
    real value. Distinguishes a genuine continuation row of a
    vertically-merged title (has other data, just no title) from a fully
    blank spacer/leftover row far below a sheet's real data (nothing but an
    auto-numbered "No" column) — the latter should never be kept, forward-
    filled or not."""
    for key, value in row.items():
        if key == primary_field or key.strip().lower() in _IGNORED_DATA_FIELDS:
            continue
        text = str(value).strip()
        if text and text.upper() != "FALSE":
            return True
    return False


def _normalize_sheet_rows(rows: list[dict[str, Any]], headers: list[str]) -> list[dict[str, Any]]:
    """A blank title cell on an otherwise-populated row almost always means
    this row sits under a title cell vertically merged in the source Google
    Sheet (e.g. several variant rows sharing one product name) — the CSV/API
    export only reports the value on the merge's first row, leaving every
    row below it blank. Carry the last real title forward onto those rows
    instead of dropping them as unlabeled "(untitled row)" noise. But a row
    with no title AND no other data at all is a genuine blank/spacer row
    (e.g. unused rows left over below a sheet's real data) — those are
    dropped entirely rather than forward-filled, otherwise they'd all get
    mislabeled as trailing "variants" of whatever product happened to be
    last."""
    primary_field = _pick_title_field(headers)
    normalized: list[dict[str, Any]] = []
    last_title = ""
    for row in rows:
        title = str(row.get(primary_field, "")).strip() if primary_field else ""
        has_data = _row_has_data(row, primary_field)
        if not title and not has_data:
            continue
        if title:
            last_title = title
        rest = {k: v for k, v in row.items() if k != primary_field}
        normalized.append({"product_name": last_title or "(untitled row)", **rest})
    return normalized


def _attach_chip_link(
    parsed_sheet, sheet_id: str, gid: str | None, header_hint: str, target_field: str,
) -> None:
    """Best-effort: find a column whose header matches header_hint and enrich
    each row in-place with the real URL behind it. The cell may hold the URL
    three different ways depending on how someone filled the sheet in: a
    Google Sheets smart-chip, a plain "insert link" hyperlink (in both cases
    the cell's plain text is just a label — the actual link only exists as
    chip/hyperlink metadata, invisible to a plain CSV export and only
    readable via the Sheets API), or the URL just typed/pasted as literal
    cell text (visible in the CSV as-is). We try the API lookup first and
    fall back to the raw text so the link survives either way, with or
    without GOOGLE_SHEETS_API_KEY configured."""
    column_index = next(
        (i for i, h in enumerate(parsed_sheet.headers) if header_hint in h.lower()),
        None,
    )
    if column_index is None:
        return
    header = parsed_sheet.headers[column_index]

    links: dict[int, str] = {}
    row_numbers = (parsed_sheet.metadata or {}).get("row_numbers") or []
    if settings.google_sheets_api_key and row_numbers:
        try:
            tab_title = fetch_sheet_tab_title(sheet_id, gid)
            links = fetch_chip_links(
                sheet_id, tab_title, column_index, min(row_numbers), max(row_numbers) + 1
            )
        except SheetFetchError as exc:
            logger.info("Skipping %s chip lookup for %s: %s", target_field, sheet_id, exc)

    for offset, row in enumerate(parsed_sheet.rows):
        raw_row_number = row_numbers[offset] if offset < len(row_numbers) else None
        link = links.get(raw_row_number) if raw_row_number is not None else None
        if not link:
            raw_value = row.get(header, "")
            if isinstance(raw_value, str) and raw_value.strip().lower().startswith(("http://", "https://")):
                link = raw_value.strip()
        if link:
            row[target_field] = link
        row.pop(header, None)


def _attach_detail_links(parsed_sheet, sheet_id: str, gid: str | None) -> None:
    _attach_chip_link(parsed_sheet, sheet_id, gid, _DETAIL_LINK_HEADER_HINT, "detail_link")
    _attach_chip_link(
        parsed_sheet, sheet_id, gid, _MARKETING_PICTURE_HEADER_HINT, "marketing_picture_link",
    )


def fetch_product_detail(url: str) -> str:
    try:
        return fetch_sheet_detail_text(url)
    except SheetFetchError as exc:
        return f"(could not open detail link: {exc})"


def _fetch_and_save_sheet(sheet_id: str, gid: str | None, url: str) -> list[dict[str, Any]]:
    csv_text = fetch_sheet_csv(sheet_id, gid)
    parsed_sheet = parse_sheet_text(csv_text, source_name=url)
    _attach_detail_links(parsed_sheet, sheet_id, gid)
    normalized_rows = _normalize_sheet_rows(parsed_sheet.rows, parsed_sheet.headers)

    file_label = f"gsheet:{sheet_id}" + (f"#gid={gid}" if gid else "")
    store = StateStore()
    store.mark_processed(file_label)
    store.save_rows(file_label, normalized_rows)
    return normalized_rows


def process_google_sheet(url: str) -> PipelineResult:
    sheet_id, gid = parse_sheet_url(url)
    normalized_rows = _fetch_and_save_sheet(sheet_id, gid, url)

    store = StateStore()
    store.link_sheet(url, sheet_id, gid)

    file_label = f"gsheet:{sheet_id}" + (f"#gid={gid}" if gid else "")
    return PipelineResult(file_name=file_label, normalized_rows=normalized_rows, issues=[])


def resync_linked_sheets() -> None:
    store = StateStore()
    for linked in store.list_linked_sheets():
        _fetch_and_save_sheet(linked["sheet_id"], linked["gid"], linked["url"])
