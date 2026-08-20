from __future__ import annotations

import hashlib
import io
import logging
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image
from googleapiclient.http import MediaIoBaseUpload

from adapters.gallery import photo_path
from adapters.google_auth import docs_service, drive_service
from adapters.llm import generate_image_from_references, generate_json
from config import settings
from core.prompts import (
    INSTRUCTION_MANUAL_FIELDS,
    build_description_prompt,
    build_instruction_manual_prompt,
    build_saran_penggunaan_image_prompt,
)

_SARAN_PENGGUNAAN_MARKER = "《AI-SARAN-PENGGUNAAN-IMAGE》"

logger = logging.getLogger(__name__)

TEMPLATE_DOC_ID = "1USMskP_kio9-4ELHVOogvcQaH4CSIBBGPkVj0KAPITI"
HISTORY_FOLDER_NAME = "Instruction Manual - History"

# Section key -> the exact heading text used for both its TOC bullet entry
# and its content heading in the template doc. Order doesn't matter here;
# _delete_disabled_sections locates each by text, not by position.
OPTIONAL_SECTION_HEADINGS: dict[str, str] = {
    "cara_penggunaan": "Petunjuk Penggunaan",
    "perawatan": "Perhatian Penggunaan",
    "gambar_produk": "Gambar Produk",
}

DESCRIPTION_TEMPLATE_DOC_IDS: dict[str, str] = {
    "goto": "1jaPwy6w0han3gP-84WQAuwDRlqDp7LDs2L-cOekiDG4",
    "gosave": "1-0oyX-dAGXFbUUvtfeVg4I0azx2PYjgEg91W9ERqefg",
    "safety_bro": "1dWxMyeOuu9mC_9_TR2vnmsLjqnfEeeFlLjgOuX6Ky4k",
}
DESCRIPTION_STORE_NAMES: dict[str, str] = {
    "goto": "GOTO Living",
    "gosave": "GOSAVE",
    "safety_bro": "SAFETYBRO",
}
DESCRIPTION_CLOSING_TAGLINES: dict[str, str] = {
    "goto": (
        "Belanja di GOTO Living adalah pilihan cerdas! Temukan produk terbaik untuk "
        "memudahkan hidup Anda dengan harga hemat, karena kebahagiaan Anda adalah "
        "prioritas kami!"
    ),
    "gosave": "Kerja lebih tenang, perlindungan lebih yakin.\nGOSAVE – Pasti Aman!",
    "safety_bro": (
        "Kalau bisa kerja aman, ngapain pilih yang bikin deg-degan?\n"
        "Percayakan semua kebutuhan perlengkapan keselamatanmu ke Safetybro, biar yang "
        "kerja kamu, bukan nasibmu!\n\n"
        "SAFETYBRO – Aman Beneran, Bukan Cuma Janji Manis."
    ),
}
DESCRIPTION_KENAPA_PILIH_BLOCKS: dict[str, str] = {
    "gosave": (
        "1. Kualitas industri terpercaya - Produk GOSAVE digunakan di banyak proyek konstruksi, "
        "manufaktur, dan workshop profesional.\n"
        "2. Ketersediaan stok besar - Siap kirim untuk kebutuhan tim atau proyek dalam jumlah "
        "banyak.\n"
        "3. Layanan B2B lengkap - Harga spesial untuk pembelian grosir, dukungan faktur pajak, "
        "dan pengiriman cepat ke seluruh Indonesia.\n"
        "4. Produk terstandar & bersertifikat - Investasi aman untuk perlengkapan kerja jangka "
        "panjang."
    ),
}
DESCRIPTION_ORDER_INFO_BLOCKS: dict[str, str] = {
    "safety_bro": (
        "Mau order banyak? Tenang, bisa banget!\n"
        "Tersedia harga spesial dan layanan faktur pajak resmi untuk kebutuhan bisnismu."
    ),
}
DESCRIPTION_FAQ_BLOCKS: dict[str, str] = {
    "gosave": (
        "1. Bisa pesan dalam jumlah besar?\n"
        "- Tentu bisa! Kami siap bantu pengadaan untuk perusahaan, proyek, atau toko dengan "
        "harga grosir dan faktur pajak resmi.\n\n"
        "2. Ada garansi produk?\n"
        "- Setiap produk dikirim dalam kondisi baru & lolos QC. Jika ada kendala, tim kami "
        "siap bantu proses klaim sesuai ketentuan."
    ),
}
DESCRIPTION_PERHATIAN_BLOCKS: dict[str, str] = {
    "goto": (
        "> Pengiriman: Produk dikemas aman dengan bahan pelindung. Estimasi pengiriman "
        "3-5 hari kerja.\n"
        "> Unboxing: Wajib merekam video saat membuka paket. Tanpa video unboxing, "
        "keluhan tidak bisa diproses.\n"
        "> Hubungi Admin: Jika ada masalah, segera hubungi admin. Kami siap membantu"
    ),
    "gosave": (
        "> Pengiriman: Produk dikemas aman dengan bahan pelindung. Estimasi pengiriman "
        "3-5 hari kerja.\n"
        "> Unboxing: Wajib merekam video saat membuka paket. Tanpa video unboxing, "
        "keluhan tidak bisa diproses.\n"
        "> Hubungi Admin: Jika ada masalah, segera hubungi admin. Kami siap membantu"
    ),
    "safety_bro": (
        "> Pengiriman: Produk dikemas aman dengan bahan pelindung. Estimasi pengiriman "
        "3-5 hari kerja.\n"
        "> Unboxing: Wajib merekam video saat membuka paket. Tanpa video unboxing, "
        "keluhan tidak bisa diproses.\n"
        "> Hubungi Admin: Jika ada masalah, segera hubungi admin. Kami siap membantu"
    ),
}
DESCRIPTION_HISTORY_FOLDER_NAME = "Deskripsi Produk - History"

_description_history_folder_id_cache: str | None = None

_history_folder_id_cache: str | None = None


def _get_history_folder_id(drive) -> str:
    """Find (or create) the Drive folder generated instruction manuals get filed
    into, so they're all in one place to browse later instead of scattered.

    The template lives on a Shared Drive, so every call here needs
    supportsAllDrives=True (and includeItemsFromAllDrives for search) or the
    folder silently ends up in the wrong Drive / the request errors out."""
    global _history_folder_id_cache

    if settings.docs_destination_folder_id:
        return settings.docs_destination_folder_id

    if _history_folder_id_cache:
        return _history_folder_id_cache

    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{HISTORY_FOLDER_NAME}' and trashed = false"
    )
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    existing = results.get("files", [])
    if existing:
        _history_folder_id_cache = existing[0]["id"]
        return _history_folder_id_cache

    template = drive.files().get(
        fileId=TEMPLATE_DOC_ID, fields="parents", supportsAllDrives=True
    ).execute()
    template_parents = template.get("parents") or []

    folder = drive.files().create(
        body={
            "name": HISTORY_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": template_parents,
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    _history_folder_id_cache = folder["id"]
    return _history_folder_id_cache


IMAGES_FOLDER_NAME = "Gambar Pendukung"

_images_folder_id_cache: str | None = None


def _get_images_folder_id(drive, history_folder_id: str) -> str:
    """Find (or create) a subfolder inside the history folder for every
    supporting image (source photos, AI-generated usage images, repaired
    template assets) uploaded along the way — keeping the main history
    folder to just the actual Instruction Manual documents instead of a flat
    mix of docs and stray image files."""
    global _images_folder_id_cache

    if _images_folder_id_cache:
        return _images_folder_id_cache

    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{IMAGES_FOLDER_NAME}' and trashed = false "
        f"and '{history_folder_id}' in parents"
    )
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    existing = results.get("files", [])
    if existing:
        _images_folder_id_cache = existing[0]["id"]
        return _images_folder_id_cache

    folder = drive.files().create(
        body={
            "name": IMAGES_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [history_folder_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    _images_folder_id_cache = folder["id"]
    return _images_folder_id_cache


def _delete_disabled_sections(docs, doc_id: str, section_labels: list[str]) -> None:
    """Remove a toggled-off section entirely from a freshly-copied doc: both
    its TOC bullet line (under "Introduction") and its heading + body content
    further down. Locates everything by matching paragraph text against
    section_labels rather than hardcoded indices, since replaceAllText token
    substitution (run right after this) shifts every index anyway. Deletes
    are collected first and applied in descending start-index order in one
    batchUpdate, so removing a later range never invalidates the index of an
    earlier one still queued."""
    if not section_labels:
        return
    targets = {label.strip().lower() for label in section_labels}

    doc = docs.documents().get(documentId=doc_id, fields="body").execute()
    content = doc.get("body", {}).get("content", [])

    headings: list[tuple[int, int, str]] = []  # (start, end, text) for every heading, not just targets
    bullet_ranges: list[tuple[int, int]] = []  # ranges to delete for matching TOC bullet lines

    for element in content:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text = "".join(
            e.get("textRun", {}).get("content", "") for e in paragraph.get("elements", [])
        ).strip()
        style = paragraph.get("paragraphStyle", {}).get("namedStyleType", "")
        if style.startswith("HEADING"):
            headings.append((element["startIndex"], element["endIndex"], text.lower()))
        elif paragraph.get("bullet") and text.lower() in targets:
            bullet_ranges.append((element["startIndex"], element["endIndex"]))

    # The Docs API rejects a deleteContentRange that reaches the very last
    # character of the body (it's the document's final newline, which can
    # never be removed) — so the last section's range must stop one short.
    doc_end = (content[-1]["endIndex"] - 1) if content else 0

    section_ranges: list[tuple[int, int]] = []
    for i, (start, _end, text) in enumerate(headings):
        if text not in targets:
            continue
        next_start = headings[i + 1][0] if i + 1 < len(headings) else doc_end
        section_ranges.append((start, next_start))

    ranges = sorted(bullet_ranges + section_ranges, key=lambda r: r[0], reverse=True)
    if not ranges:
        return

    requests = [
        {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}}
        for start, end in ranges
    ]
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def _get_description_history_folder_id(drive) -> str:
    """Find (or create) the Drive folder generated product descriptions get filed
    into, mirroring _get_history_folder_id's pattern for instruction manuals."""
    global _description_history_folder_id_cache
    if _description_history_folder_id_cache:
        return _description_history_folder_id_cache

    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{DESCRIPTION_HISTORY_FOLDER_NAME}' and trashed = false"
    )
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    existing = results.get("files", [])
    if existing:
        _description_history_folder_id_cache = existing[0]["id"]
        return _description_history_folder_id_cache

    any_template_id = next(iter(DESCRIPTION_TEMPLATE_DOC_IDS.values()))
    template = drive.files().get(
        fileId=any_template_id, fields="parents", supportsAllDrives=True
    ).execute()
    template_parents = template.get("parents") or []

    folder = drive.files().create(
        body={
            "name": DESCRIPTION_HISTORY_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": template_parents,
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    _description_history_folder_id_cache = folder["id"]
    return _description_history_folder_id_cache


_DESCRIPTION_HEADER_FONT = {"fontFamily": "Arial"}
_DESCRIPTION_HEADER_SIZE_PT = 10
_DESCRIPTION_BODY_FONT = {"fontFamily": "Calibri"}
_DESCRIPTION_BODY_SIZE_PT = 12


def _apply_description_font_styles(docs, doc_id: str, product_name: str, store_name: str) -> None:
    """Force the product-name and store-name lines (the doc's only "header")
    to Arial 10 Bold, and every other paragraph — including the "Spesifikasi:"
    / "FAQ" / etc. section headings, which are body text for styling purposes
    — to Calibri 12 regular. Applied regardless of whatever font the
    template's placeholder text happened to carry, so generated description
    docs stay visually consistent across brands even if a template drifts."""
    header_texts = {product_name.strip(), store_name.strip()}

    doc = docs.documents().get(documentId=doc_id, fields="body").execute()
    content = doc.get("body", {}).get("content", [])

    requests: list[dict[str, Any]] = []
    for element in content:
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        start, end = element["startIndex"], element["endIndex"]
        if end <= start:
            continue
        text = "".join(
            e.get("textRun", {}).get("content", "") for e in paragraph.get("elements", [])
        )
        if text.strip() in header_texts:
            text_style = {
                "weightedFontFamily": _DESCRIPTION_HEADER_FONT,
                "bold": True,
                "fontSize": {"magnitude": _DESCRIPTION_HEADER_SIZE_PT, "unit": "PT"},
            }
        else:
            text_style = {
                "weightedFontFamily": _DESCRIPTION_BODY_FONT,
                "bold": False,
                "fontSize": {"magnitude": _DESCRIPTION_BODY_SIZE_PT, "unit": "PT"},
            }
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": text_style,
                "fields": "weightedFontFamily,bold,fontSize",
            }
        })

    if requests:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def _clean_description_template_block(lines: list[str]) -> str:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(line.strip() for line in lines).strip()


def _parse_description_template_text(template_text: str) -> dict[str, str]:
    section_map = {
        "INTRO": "INTRO_PARAGRAPH",
        "KEUNGGULAN": "SELLING_POINTS_BLOCK",
        "SPESIFIKASI": "SPEC_LINES",
        "VARIAN": "VARIAN_LIST_BLOCK",
        "FAQ": "FAQ_BLOCK",
    }
    headings = {"DESCRIPTION_TEMPLATE", "NAMA_PRODUK", "VENDOR", *section_map.keys()}
    blocks: dict[str, list[str]] = {}
    current: str | None = None

    for raw_line in template_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        key, separator, value = line.partition(":")
        normalized_key = key.strip().upper()

        if line.upper() == "DESCRIPTION_TEMPLATE":
            current = None
            continue
        if separator and normalized_key in headings:
            current = normalized_key
            blocks[current] = [value.strip()] if value.strip() else []
            continue
        if current:
            blocks.setdefault(current, []).append(raw_line.rstrip())

    values: dict[str, str] = {}
    for template_heading, field in section_map.items():
        value = _clean_description_template_block(blocks.get(template_heading, []).copy())
        if value:
            values[field] = value
    return values


def generate_description_doc(
    row: dict[str, Any],
    brand: str,
    detail_text: str | None = None,
    template_text: str | None = None,
) -> str:
    """Generate a filled-in marketplace product description Google Doc for one
    product, by copying that brand's placeholder template and replacing each
    {{TOKEN}} — the AI-written fields (intro, selling points, spec lines, FAQ)
    plus the brand's fixed store name / closing tagline / "PERHATIAN!" notice,
    which stay the same for every product rather than being re-generated."""
    template_id = DESCRIPTION_TEMPLATE_DOC_IDS.get(brand)
    if not template_id:
        raise ValueError(f"No description template configured for brand '{brand}'")

    product_name = str(row.get("product_name") or "Untitled Product")

    generated = _parse_description_template_text(template_text) if template_text else None
    if generated is None:
        prompt = build_description_prompt(row, detail_text)
        generated = generate_json(prompt)

    def _block(field: str) -> str:
        value = str(generated.get(field) or "-").strip()
        value = value.replace("\\n", "\x0b").replace("\n", "\x0b")
        # Strip stray leading/trailing soft breaks too — the AI sometimes emits
        # a literal "\n" at the very start/end of a field's JSON string value,
        # which survives the plain .strip() above (it isn't whitespace until
        # after the \\n -> \x0b conversion) and would otherwise show up as a
        # phantom blank line before/after that field in the generated doc.
        value = value.strip("\x0b").strip()
        return value or "-"

    values: dict[str, str] = {
        "PRODUCT_NAME": product_name,
        "STORE_NAME": DESCRIPTION_STORE_NAMES[brand],
        "INTRO_PARAGRAPH": _block("INTRO_PARAGRAPH"),
        "SELLING_POINTS_BLOCK": _block("SELLING_POINTS_BLOCK"),
        "SPEC_LINES": _block("SPEC_LINES"),
        "VARIAN_LIST_BLOCK": _block("VARIAN_LIST_BLOCK"),
        "FAQ_BLOCK": (
            DESCRIPTION_FAQ_BLOCKS[brand].replace("\n", "\x0b")
            if brand in DESCRIPTION_FAQ_BLOCKS
            else _block("FAQ_BLOCK")
        ),
        "CLOSING_TAGLINE": DESCRIPTION_CLOSING_TAGLINES[brand].replace("\n", "\x0b"),
        "KENAPA_PILIH_BLOCK": DESCRIPTION_KENAPA_PILIH_BLOCKS.get(brand, "-").replace("\n", "\x0b"),
        "PERHATIAN_BLOCK": DESCRIPTION_PERHATIAN_BLOCKS[brand].replace("\n", "\x0b"),
        "ORDER_INFO_BLOCK": DESCRIPTION_ORDER_INFO_BLOCKS.get(brand, "-").replace("\n", "\x0b"),
    }

    drive = drive_service()
    history_folder_id = _get_description_history_folder_id(drive)

    copy = drive.files().copy(
        fileId=template_id,
        body={"name": f"Deskripsi - {product_name}", "parents": [history_folder_id]},
        supportsAllDrives=True,
    ).execute()
    new_doc_id = copy["id"]

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": "{{" + key + "}}", "matchCase": True},
                "replaceText": value,
            }
        }
        for key, value in values.items()
    ]
    # Template docs are saved as "Pageless" — force every generated copy back
    # to a normal paginated ("Pages") layout regardless of the template's
    # current setting.
    requests.append({
        "updateDocumentStyle": {
            "documentStyle": {"documentFormat": {"documentMode": "PAGES"}},
            "fields": "documentFormat",
        }
    })
    docs = docs_service()
    docs.documents().batchUpdate(documentId=new_doc_id, body={"requests": requests}).execute()
    _apply_description_font_styles(docs, new_doc_id, product_name, DESCRIPTION_STORE_NAMES[brand])

    return f"https://docs.google.com/document/d/{new_doc_id}/edit"


def get_description_history_folder_url() -> str:
    drive = drive_service()
    folder_id = _get_description_history_folder_id(drive)
    return f"https://drive.google.com/drive/folders/{folder_id}"


def list_description_history_docs() -> list[dict[str, str]]:
    drive = drive_service()
    folder_id = _get_description_history_folder_id(drive)

    results = drive.files().list(
        q=(
            f"'{folder_id}' in parents and trashed = false "
            "and mimeType = 'application/vnd.google-apps.document'"
        ),
        fields="files(id, name, webViewLink, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()

    return [
        {
            "id": f["id"],
            "name": f["name"],
            "url": f.get("webViewLink") or f"https://docs.google.com/document/d/{f['id']}/edit",
            "modified_at": f.get("modifiedTime"),
        }
        for f in results.get("files", [])
    ]


def write_doc(title: str, body: str, destination_folder_id: str | None = None) -> dict[str, Any]:
    return {
        "title": title,
        "body": body,
        "destination_folder_id": destination_folder_id,
        "path": str(Path("/tmp") / f"{title.replace(' ', '_')}.md"),
    }


_DRIVE_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_DRIVE_FILE_RE = re.compile(r"/file/d/([a-zA-Z0-9_-]+)")
_DRIVE_ID_PARAM_RE = re.compile(r"[?&]id=([a-zA-Z0-9_-]+)")


_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _list_images_in_folder_recursive(
    drive, folder_id: str, *, max_depth: int = 4, max_results: int = 60,
) -> list[dict[str, str]]:
    """Collect every image file under folder_id, including ones nested in
    subfolders — the sheet's marketing picture folder sometimes organizes
    photos into subfolders (by color, angle, etc.) instead of dropping them
    all directly inside it. Breadth-first, capped at max_depth levels and
    max_results images so a huge/misconfigured folder tree can't run away."""
    images: list[dict[str, str]] = []
    queue: list[tuple[str, int]] = [(folder_id, 0)]

    while queue and len(images) < max_results:
        current_id, depth = queue.pop(0)
        try:
            results = drive.files().list(
                q=f"'{current_id}' in parents and trashed = false",
                fields="files(id, name, mimeType)",
                orderBy="name",
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
            ).execute()
        except Exception:
            logger.exception("Failed to list Drive folder %s", current_id)
            continue

        for f in results.get("files", []):
            mime = f.get("mimeType", "")
            if mime.startswith("image/"):
                images.append({"id": f["id"], "name": f["name"]})
                if len(images) >= max_results:
                    break
            elif mime == _FOLDER_MIME_TYPE and depth < max_depth:
                queue.append((f["id"], depth + 1))

    return images


def _resolve_drive_file_id(drive, url: str) -> str | None:
    """Resolve a Google Drive link (file or folder) to the id of an actual
    image FILE, without downloading anything. The "LINK MARKETING PICTURE"
    column usually points at a Drive FOLDER of marketing pictures for that
    product rather than a single image file — in that case the first image
    found (searching subfolders too) is used."""
    folder_match = _DRIVE_FOLDER_RE.search(url)
    if folder_match:
        images = _list_images_in_folder_recursive(drive, folder_match.group(1), max_results=1)
        return images[0]["id"] if images else None

    file_match = _DRIVE_FILE_RE.search(url) or _DRIVE_ID_PARAM_RE.search(url)
    return file_match.group(1) if file_match else None


def _normalize_to_png_bytes(content: bytes) -> bytes | None:
    """Re-encode arbitrary downloaded image bytes (jpg, webp, etc.) as PNG so
    they're safe to hand to the Gemini vision call and to Drive uploads with a
    fixed image/png mime type. Returns None if the bytes aren't a decodable
    image at all."""
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def list_marketing_picture_candidates(marketing_link: str) -> list[dict[str, str]]:
    """Resolve the sheet's LINK MARKETING PICTURE column to every candidate
    image the user could pick from — every image under the folder if it's a
    Drive folder link, including ones nested in subfolders (rather than
    only the ones sitting directly inside it), or the single file if it's a
    direct Drive file link. A plain (non-Drive) image URL isn't a Drive
    file, so it isn't listable here — the caller should keep treating that
    case as a single automatic photo, same as before."""
    link = (marketing_link or "").strip()
    if not link:
        return []

    folder_match = _DRIVE_FOLDER_RE.search(link)
    if folder_match:
        drive = drive_service()
        return _list_images_in_folder_recursive(drive, folder_match.group(1))

    file_match = _DRIVE_FILE_RE.search(link) or _DRIVE_ID_PARAM_RE.search(link)
    if file_match:
        return [{"id": file_match.group(1), "name": "photo"}]

    return []


def fetch_marketing_picture_candidate_bytes(file_id: str) -> bytes | None:
    """Download one specific candidate image by Drive file id, as returned
    by list_marketing_picture_candidates."""
    try:
        drive = drive_service()
        content = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    except Exception:
        logger.exception("Failed to fetch marketing picture candidate %s", file_id)
        return None
    return _normalize_to_png_bytes(content) if content else None


def fetch_marketing_picture_bytes(marketing_link: str) -> bytes | None:
    """Resolve the sheet's LINK MARKETING PICTURE column — a Drive file link,
    a Drive folder link (first image inside is used), or a plain image URL —
    to actual image bytes, normalized to PNG. Returns None if nothing usable
    was found (empty link, private/inaccessible file, not an image, etc.)."""
    link = (marketing_link or "").strip()
    if not link:
        return None

    content: bytes | None = None
    try:
        drive = drive_service()
        file_id = _resolve_drive_file_id(drive, link)
        if file_id:
            content = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
    except Exception:
        logger.exception("Failed to fetch marketing picture via Drive API: %s", link)
        content = None

    if content is None:
        content = _download(link)

    return _normalize_to_png_bytes(content) if content else None


def _fetch_reference_images(
    drive, row: dict[str, Any], product_name: str, count: int,
) -> list[bytes]:
    """Fetch up to `count` real product photos to ground the AI's "Saran
    Penggunaan" writeup in what the product actually looks like, instead of
    guessing generically. Prefers the vendor sheet's "LINK MARKETING PICTURE"
    Drive folder (using more angles gives the model more to reason about);
    falls back to whatever single photo is available (a direct file link, or
    the Gallery-uploaded photo) if a folder with multiple images isn't there."""
    images: list[bytes] = []
    marketing_link = str(row.get("marketing_picture_link") or "").strip()

    if marketing_link:
        try:
            folder_match = _DRIVE_FOLDER_RE.search(marketing_link)
            if folder_match:
                results = drive.files().list(
                    q=f"'{folder_match.group(1)}' in parents and mimeType contains "
                    "'image/' and trashed = false",
                    fields="files(id, name)",
                    orderBy="name",
                    pageSize=count,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives",
                ).execute()
                files = results.get("files", [])[:count]

                def _process(f):
                    thread_drive = drive_service()
                    content = thread_drive.files().get_media(
                        fileId=f["id"], supportsAllDrives=True,
                    ).execute()
                    return _normalize_to_png_bytes(content)

                if files:
                    with ThreadPoolExecutor(max_workers=len(files)) as executor:
                        images.extend(img for img in executor.map(_process, files) if img)
            else:
                file_id = _resolve_drive_file_id(drive, marketing_link)
                content = (
                    drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
                    if file_id
                    else _download(marketing_link)
                )
                normalized = _normalize_to_png_bytes(content) if content else None
                if normalized:
                    images.append(normalized)
        except Exception:
            logger.exception("Failed to fetch marketing reference images for %s", product_name)

    if not images:
        path = photo_path(product_name)
        if path.exists():
            normalized = _normalize_to_png_bytes(path.read_bytes())
            if normalized:
                images.append(normalized)

    return images


def _generate_saran_penggunaan_images(
    drive, row: dict[str, Any], product_name: str, image_count: int,
) -> list[bytes]:
    """Best-effort: generate `image_count` distinct images for the "Saran
    Penggunaan" section, each grounded in the product's real reference
    photo(s) so the AI-drawn usage scenes still show the actual product.
    Returns fewer than `image_count` (even an empty list, leaving the
    section empty) if no reference photo is available at all, or if some of
    the individual generation calls fail — a partial result is used rather
    than discarding the ones that did succeed."""
    images = _fetch_reference_images(drive, row, product_name, image_count)
    if not images:
        return []

    def _generate_one(i: int) -> bytes | None:
        prompt = build_saran_penggunaan_image_prompt(row, variation_index=i)
        try:
            return generate_image_from_references(prompt, images)
        except Exception:
            logger.exception("Failed to generate a Saran Penggunaan image for %s", product_name)
            return None

    # Each image is an independent, slow (network-bound) Gemini call — run
    # them concurrently instead of one after another so requesting 3 images
    # doesn't take ~3x as long as requesting 1.
    with ThreadPoolExecutor(max_workers=image_count) as executor:
        generated = list(executor.map(_generate_one, range(image_count)))
    results = [image for image in generated if image is not None]

    return results


_SARAN_PENGGUNAAN_IMAGE_SIZE_PT = 260


def _find_marker_delete_range(docs, doc_id: str, marker: str) -> tuple[int, int] | None:
    """Locate the range to clear out before inserting the Saran Penggunaan
    image: the marker text itself, plus anything else already sharing its
    paragraph. The template's decorative divider image sits in the same
    paragraph as the marker — deleting only the marker text would leave that
    divider sitting right next to the new image instead of being replaced by
    it, so the whole paragraph's content up to (not including) the marker's
    own trailing newline is cleared instead."""
    doc = docs.documents().get(documentId=doc_id, fields="body").execute()
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for el in paragraph.get("elements", []):
            text_run = el.get("textRun")
            if not text_run:
                continue
            content = text_run.get("content", "")
            offset = content.find(marker)
            if offset == -1:
                continue
            marker_start = el["startIndex"] + offset
            marker_end = marker_start + len(marker)
            return element["startIndex"], marker_end
    return None


def _insert_marker_images(docs, doc_id: str, marker: str, image_urls: list[str]) -> None:
    """Replace a text marker (see _SARAN_PENGGUNAAN_MARKER) — and anything
    else sharing its paragraph, e.g. the template's leftover divider image —
    with one or more AI-generated images, each sized to a fixed, sane box
    instead of the API's default (which scales an image up to the full page
    width). Multiple images are inserted right after each other in order."""
    if not image_urls:
        return
    delete_range = _find_marker_delete_range(docs, doc_id, marker)
    if delete_range is None:
        return
    start, end = delete_range

    image_size = {
        "height": {"magnitude": _SARAN_PENGGUNAAN_IMAGE_SIZE_PT, "unit": "PT"},
        "width": {"magnitude": _SARAN_PENGGUNAAN_IMAGE_SIZE_PT, "unit": "PT"},
    }
    requests: list[dict[str, Any]] = [
        {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}},
    ]
    # Inserted in reverse so each ends up to the LEFT of the one before it
    # (repeated inserts at the same anchor index push earlier-inserted
    # content rightward) — net result is left-to-right order matching
    # image_urls, same trick used for the "Gambar Produk" photos.
    for url in reversed(image_urls):
        requests.append({
            "insertInlineImage": {
                "location": {"index": start},
                "uri": url,
                "objectSize": image_size,
            }
        })
    docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def _drive_thumbnail_url(drive, file_id: str) -> str:
    """A URL Google's own servers can fetch back for a file already on Drive
    (needed by the Docs API's replaceImage request). Grants "anyone with the
    link can view" if the file doesn't already have it — required for the
    Docs API to be able to fetch it as a plain URL."""
    try:
        drive.permissions().create(
            fileId=file_id,
            body={"role": "reader", "type": "anyone"},
            supportsAllDrives=True,
        ).execute()
    except Exception:
        logger.exception("Failed to grant read access to Drive file %s", file_id)
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w1000"


def _upload_bytes_and_get_url(drive, content: bytes, product_name: str, folder_id: str) -> str | None:
    """Upload raw image bytes (from an external URL or a locally uploaded
    Gallery photo — anything NOT already sitting on Drive) to the history
    folder and return a fetchable URL for it, same as _drive_thumbnail_url."""
    try:
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype="image/png")
        uploaded = drive.files().create(
            body={"name": f"{product_name} - source photo.png", "parents": [folder_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return _drive_thumbnail_url(drive, uploaded["id"])
    except Exception:
        logger.exception("Failed to upload product photo for %s", product_name)
        return None


# Matches the "Gambar Produk" placeholder box's own aspect ratio (roughly
# 293:391 pt in the template) — used to center-crop every product photo to
# the same shape before upload, so multiple photos placed side by side
# render at consistent sizes instead of each keeping its own native aspect
# ratio (which made a portrait photo end up a different width than a
# square one).
_PRODUCT_PHOTO_ASPECT_RATIO = 3 / 4


def _crop_to_aspect_png(content: bytes, aspect_ratio: float) -> bytes | None:
    """Center-crop image bytes to a fixed width/height aspect ratio — never
    stretching or distorting, just trimming the longer dimension evenly from
    both sides. Returns None if the bytes aren't a decodable image."""
    try:
        image = Image.open(io.BytesIO(content)).convert("RGB")
    except Exception:
        return None

    width, height = image.size
    if width / height > aspect_ratio:
        new_width = round(height * aspect_ratio)
        left = (width - new_width) // 2
        image = image.crop((left, 0, left + new_width, height))
    else:
        new_height = round(width / aspect_ratio)
        top = (height - new_height) // 2
        image = image.crop((0, top, width, top + new_height))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_cropped_product_photo(drive, content: bytes, product_name: str, folder_id: str) -> str | None:
    cropped = _crop_to_aspect_png(content, _PRODUCT_PHOTO_ASPECT_RATIO) or content
    return _upload_bytes_and_get_url(drive, cropped, product_name, folder_id)


def _resolve_product_photo_urls(
    drive, row: dict[str, Any], product_name: str, folder_id: str, count: int = 1,
) -> list[str]:
    """Get up to `count` Docs-API-fetchable URLs for the product's real
    photos, preferring the vendor sheet's own "LINK MARKETING PICTURE"
    column (the real URL behind that cell's hyperlink chip, attached as
    row["marketing_picture_link"] during sheet processing — see
    services/pipeline.py) and falling back to a photo already uploaded
    through the Gallery feature if that column is empty or fails to resolve.
    Every photo is center-cropped to a consistent aspect ratio and
    re-uploaded (see _crop_to_aspect_png) so multiple product angles render
    at uniform, tidy sizes in the doc rather than each keeping its own
    native shape. Returns fewer than `count` (even zero) if that's genuinely
    all that's available — never invents extra photos."""
    marketing_link = str(row.get("marketing_picture_link") or "").strip()
    if marketing_link:
        folder_match = _DRIVE_FOLDER_RE.search(marketing_link)
        if folder_match:
            try:
                results = drive.files().list(
                    q=f"'{folder_match.group(1)}' in parents and mimeType contains "
                    "'image/' and trashed = false",
                    fields="files(id, name)",
                    orderBy="name",
                    pageSize=count,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora="allDrives",
                ).execute()
                files = results.get("files", [])[:count]

                def _process(f):
                    # A fresh service per thread — googleapiclient's Resource
                    # objects wrap an httplib2.Http that isn't safe to share
                    # across concurrent requests.
                    thread_drive = drive_service()
                    content = thread_drive.files().get_media(
                        fileId=f["id"], supportsAllDrives=True,
                    ).execute()
                    return _upload_cropped_product_photo(thread_drive, content, product_name, folder_id)

                if files:
                    with ThreadPoolExecutor(max_workers=len(files)) as executor:
                        urls = [url for url in executor.map(_process, files) if url]
                    if urls:
                        return urls
            except Exception:
                logger.exception("Failed to list marketing picture folder for %s", product_name)

        file_id = _resolve_drive_file_id(drive, marketing_link)
        if file_id:
            content = drive.files().get_media(fileId=file_id, supportsAllDrives=True).execute()
            url = _upload_cropped_product_photo(drive, content, product_name, folder_id) if content else None
            if url:
                return [url]

        content = _download(marketing_link)
        if content:
            url = _upload_cropped_product_photo(drive, content, product_name, folder_id)
            return [url] if url else []

        logger.warning(
            "Could not resolve LINK MARKETING PICTURE for %s: %s", product_name, marketing_link,
        )

    path = photo_path(product_name)
    if path.exists():
        url = _upload_cropped_product_photo(drive, path.read_bytes(), product_name, folder_id)
        return [url] if url else []

    return []


def _replace_placeholder_images(docs, new_doc_id: str, image_urls: list[str]) -> None:
    """Fill the "Gambar Produk" section with the product's real photos:
    swap the template's placeholder image for the first photo, then insert
    any additional photos (up to what's available) right after it at the
    same size, so multiple real product angles show up instead of just one.
    Only touches an inline image whose content matches a known placeholder
    hash — the template also has other inline images (e.g. a title accent
    bar) that must stay untouched. Applied as its own batchUpdate, separate
    from the text token replacements, since it needs the copy's own
    inlineObjects (new objectIds minted on copy, not the template's)."""
    if not image_urls:
        return

    placeholder_hashes = _get_template_placeholder_hashes()
    if not placeholder_hashes:
        return

    doc = docs.documents().get(documentId=new_doc_id, fields="inlineObjects,body").execute()
    inline_objects = doc.get("inlineObjects", {})

    match: tuple[str, int] | None = None
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for el in paragraph.get("elements", []):
            image_el = el.get("inlineObjectElement")
            if not image_el:
                continue
            object_id = image_el["inlineObjectId"]
            uri = (
                inline_objects.get(object_id, {})
                .get("inlineObjectProperties", {})
                .get("embeddedObject", {})
                .get("imageProperties", {})
                .get("contentUri")
            )
            if not uri:
                continue
            content = _download(uri)
            if content and hashlib.sha256(content).hexdigest() in placeholder_hashes:
                match = (object_id, el["endIndex"])
                break
        if match:
            break

    if match is None:
        return

    object_id, anchor_index = match
    size = (
        inline_objects.get(object_id, {})
        .get("inlineObjectProperties", {})
        .get("embeddedObject", {})
        .get("size")
    )

    requests: list[dict[str, Any]] = [
        {"replaceImage": {"imageObjectId": object_id, "uri": image_urls[0]}}
    ]
    extra_urls = image_urls[1:]
    if extra_urls and size:
        # Inserted in reverse so each ends up to the LEFT of the one before
        # it in the batch (repeated inserts at the same anchor index push
        # earlier-inserted content rightward) — net result is left-to-right
        # order matching image_urls.
        for url in reversed(extra_urls):
            requests.append({
                "insertInlineImage": {
                    "location": {"index": anchor_index},
                    "uri": url,
                    "objectSize": size,
                }
            })

    docs.documents().batchUpdate(documentId=new_doc_id, body={"requests": requests}).execute()


def generate_instruction_manual_doc(
    row: dict[str, Any],
    detail_text: str | None = None,
    image_count: int = 1,
    sections: dict[str, bool] | None = None,
) -> str:
    """Generate a filled-in Instruction Manual Google Doc for one product,
    by copying the placeholder template and replacing each {{TOKEN}} with
    either a direct field from the sheet row or AI-written content.
    image_count controls both how many real product reference photos (from
    the sheet's marketing-picture folder) are shown to the AI, and how many
    distinct "Saran Penggunaan" usage images get generated and inserted.
    sections toggles the optional sections in OPTIONAL_SECTION_HEADINGS off
    (default: all enabled) — a disabled section is skipped in generation
    (no wasted AI call / photo lookup) and removed from the doc entirely,
    TOC entry included."""
    product_name = str(row.get("product_name") or "Untitled Product")
    sections = sections or {}
    gambar_produk_enabled = sections.get("gambar_produk", True)
    disabled_labels = [
        label for key, label in OPTIONAL_SECTION_HEADINGS.items() if not sections.get(key, True)
    ]
    if not gambar_produk_enabled:
        # "Saran Penggunaan" (AI-generated usage photos) rides on the same
        # toggle as "Gambar Produk" (real product photos) rather than
        # getting its own checkbox — disabling one product-photo section
        # without the other left an orphan image in the doc.
        disabled_labels.append("Saran Penggunaan")

    prompt = build_instruction_manual_prompt(row, detail_text, sections)
    generated = generate_json(prompt)

    brand_word = product_name.split()[0] if product_name.split() else product_name

    drive = drive_service()

    values: dict[str, str] = {"PRODUCT_NAME": product_name, "ITEM_NAME": product_name}
    values["MEREK"] = brand_word
    values["TIPE"] = str(row.get("Parent ID / Tipe / Jenis / Model") or generated.get("TIPE") or "-")
    values["MADE_IN"] = "China"

    for field in INSTRUCTION_MANUAL_FIELDS:
        if field in values:
            continue
        value = str(generated.get(field) or "-").strip() or "-"
        value = value.replace("\\n", "\x0b").replace("\n", "\x0b")
        values[field] = value

    history_folder_id = _get_history_folder_id(drive)
    images_folder_id = _get_images_folder_id(drive, history_folder_id)

    # These two are independent of each other (one talks to Gemini, one to
    # Drive) — run them at the same time instead of one after the other so
    # picking 3 images doesn't add up two separate multi-second waits. Each
    # gets its own drive_service() since the underlying http client isn't
    # safe to share across threads.
    with ThreadPoolExecutor(max_workers=2) as executor:
        saran_future = (
            executor.submit(
                _generate_saran_penggunaan_images, drive_service(), row, product_name, image_count,
            )
            if gambar_produk_enabled
            else None
        )
        photos_future = (
            executor.submit(
                _resolve_product_photo_urls, drive_service(), row, product_name, images_folder_id, 3,
            )
            if gambar_produk_enabled
            else None
        )
        saran_penggunaan_images = saran_future.result() if saran_future else []
        image_urls = photos_future.result() if photos_future else []

    values["SARAN_PENGGUNAAN"] = _SARAN_PENGGUNAAN_MARKER if saran_penggunaan_images else "-"

    copy = drive.files().copy(
        fileId=TEMPLATE_DOC_ID,
        body={"name": f"Instruction Manual - {product_name}", "parents": [history_folder_id]},
        supportsAllDrives=True,
    ).execute()
    new_doc_id = copy["id"]
    docs = docs_service()

    if disabled_labels:
        _delete_disabled_sections(docs, new_doc_id, disabled_labels)

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": "{{" + key + "}}", "matchCase": True},
                "replaceText": value,
            }
        }
        for key, value in values.items()
    ]
    docs.documents().batchUpdate(documentId=new_doc_id, body={"requests": requests}).execute()

    if image_urls:
        try:
            _replace_placeholder_images(docs, new_doc_id, image_urls)
        except Exception:
            logger.exception("Failed to insert product photo into doc for %s", product_name)

    if saran_penggunaan_images:
        try:
            def _upload_one(image_bytes: bytes) -> str | None:
                # Fresh service per thread — see the same note in
                # _resolve_product_photo_urls.
                thread_drive = drive_service()
                return _upload_bytes_and_get_url(
                    thread_drive, image_bytes, f"{product_name} - saran penggunaan", images_folder_id,
                )

            with ThreadPoolExecutor(max_workers=len(saran_penggunaan_images)) as executor:
                saran_image_urls = [
                    url for url in executor.map(_upload_one, saran_penggunaan_images) if url
                ]
            if saran_image_urls:
                _insert_marker_images(docs, new_doc_id, _SARAN_PENGGUNAAN_MARKER, saran_image_urls)
        except Exception:
            logger.exception("Failed to insert Saran Penggunaan images for %s", product_name)

    return f"https://docs.google.com/document/d/{new_doc_id}/edit"


PDF_TRANSLATIONS_FOLDER_NAME = "PDF Translations"

_pdf_translations_folder_id_cache: str | None = None


def _get_pdf_translations_folder_id(drive, history_folder_id: str) -> str:
    """Find (or create) a subfolder inside the history folder to keep
    translated-PDF docs separate from Instruction Manual docs."""
    global _pdf_translations_folder_id_cache

    if _pdf_translations_folder_id_cache:
        return _pdf_translations_folder_id_cache

    query = (
        "mimeType = 'application/vnd.google-apps.folder' "
        f"and name = '{PDF_TRANSLATIONS_FOLDER_NAME}' and trashed = false "
        f"and '{history_folder_id}' in parents"
    )
    results = drive.files().list(
        q=query,
        fields="files(id, name)",
        pageSize=1,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()
    existing = results.get("files", [])
    if existing:
        _pdf_translations_folder_id_cache = existing[0]["id"]
        return _pdf_translations_folder_id_cache

    folder = drive.files().create(
        body={
            "name": PDF_TRANSLATIONS_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [history_folder_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    _pdf_translations_folder_id_cache = folder["id"]
    return _pdf_translations_folder_id_cache


_DOCS_MAX_INSERT_TEXT_CHARS = 900_000  # Docs API request body limit is ~1MB; stays comfortably under it.


def _parse_translated_blocks(text: str) -> list[dict[str, str]]:
    """Turn the lightweight '# heading' / '- bullet' markup (see
    core.prompts.build_pdf_translate_prompt) into a flat list of
    {"type", "text"} blocks, one per non-empty line — blank lines just
    separate paragraphs and don't become blocks of their own."""
    blocks: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append({"type": "heading", "text": line[2:].strip()})
        elif line.startswith("- "):
            blocks.append({"type": "bullet", "text": line[2:].strip()})
        else:
            blocks.append({"type": "paragraph", "text": line})
    return blocks


_NO_MARKER_RE = re.compile(r"^\s*no\.?\s*(\d+)", re.IGNORECASE)


def _no_marker_key(text: str | None) -> str | None:
    """Match ONLY the "NO.1" / "NO. 2" / "no3" style step marker specifically
    used for this diagram/step pairing — deliberately narrow (vs. matching
    any leading digit) since a page can have several unrelated numbered
    lists (install notes, product components, steps), and a bare-digit match
    risks pairing a diagram to the wrong list's item. The translated text's
    "NO.X" marker may end up as either its own heading or the start of a
    bullet line depending on how the AI formatted that page, so this is
    checked against every block, not just headings."""
    if not text:
        return None
    match = _NO_MARKER_RE.match(text.strip())
    return match.group(1) if match else None


_TRANSLATED_PAGE_IMAGE_MAX_WIDTH_PT = 400


def _page_image_object_size(image_bytes: bytes) -> dict[str, Any]:
    """Fit a rendered PDF page image to a fixed max width, preserving its
    aspect ratio, so a landscape diagram and a portrait page both render at
    a sane, consistent size instead of the API's default full-page-width
    scaling."""
    width_px, height_px = Image.open(io.BytesIO(image_bytes)).size
    width_pt = _TRANSLATED_PAGE_IMAGE_MAX_WIDTH_PT
    height_pt = width_pt * (height_px / width_px)
    return {
        "width": {"magnitude": width_pt, "unit": "PT"},
        "height": {"magnitude": height_pt, "unit": "PT"},
    }


def create_translated_pdf_doc(title: str, pages: list[dict[str, Any]]) -> str:
    """Create a new, blank Google Doc (not from any template) containing the
    translated PDF text, filed into its own "PDF Translations" subfolder of
    the shared history folder. Headings become real Docs heading paragraphs
    and bullet lines become a real bulleted list, based on the '# ' / '- '
    markup the translation prompt is instructed to produce. Each page's
    embedded images (see adapters.pdf_translate — the actual diagrams/photos
    in the source PDF, not a screenshot of the whole page) are inserted right
    after that page's translated text, in original page order, so
    illustrations aren't lost or duplicated alongside their own text.
    Returns the doc's edit URL."""
    drive = drive_service()
    history_folder_id = _get_history_folder_id(drive)
    folder_id = _get_pdf_translations_folder_id(drive, history_folder_id)

    doc = drive.files().create(
        body={
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [folder_id],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    doc_id = doc["id"]
    docs = docs_service()

    if not pages:
        return f"https://docs.google.com/document/d/{doc_id}/edit"

    # Flatten to one (page_number, image_index, image dict) entry per image
    # so every image — pages can have zero, one, or several — gets its own
    # concurrent upload.
    image_entries: list[tuple[int, int, dict[str, Any]]] = [
        (page_number, image_index, image)
        for page_number, page in enumerate(pages)
        for image_index, image in enumerate(page.get("images") or [])
    ]

    def _upload_one(entry: tuple[int, int, dict[str, Any]]) -> str | None:
        page_number, image_index, image = entry
        thread_drive = drive_service()
        label = f"{title} - page {page_number + 1} image {image_index + 1}"
        return _upload_bytes_and_get_url(thread_drive, image["image_bytes"], label, folder_id)

    uploaded_urls: list[str | None] = []
    if image_entries:
        with ThreadPoolExecutor(max_workers=min(len(image_entries), 4)) as executor:
            uploaded_urls = list(executor.map(_upload_one, image_entries))

    # Re-group uploaded images back per page (each carrying its own url,
    # bytes, and reference_marker), in original per-page order.
    images_by_page: dict[int, list[dict[str, Any]]] = {}
    for (page_number, _image_index, image), url in zip(image_entries, uploaded_urls):
        if url:
            images_by_page.setdefault(page_number, []).append({**image, "url": url})

    requests: list[dict[str, Any]] = []
    style_requests: list[dict[str, Any]] = []
    index = 1
    remaining_chars = _DOCS_MAX_INSERT_TEXT_CHARS

    def _insert_image(image: dict[str, Any]) -> None:
        nonlocal index
        try:
            object_size = _page_image_object_size(image["image_bytes"])
        except Exception:
            logger.exception("Failed to size translated page image for %s", title)
            return
        requests.append({
            "insertInlineImage": {
                "location": {"index": index},
                "uri": image["url"],
                "objectSize": object_size,
            }
        })
        index += 1
        requests.append({"insertText": {"location": {"index": index}, "text": "\n\n"}})
        index += 2

    def _insert_text_blocks(blocks: list[dict[str, str]]) -> None:
        nonlocal index
        if not blocks:
            return
        text = "".join(f"{block['text']}\n" for block in blocks)
        requests.append({"insertText": {"location": {"index": index}, "text": text}})
        block_index = index
        for block in blocks:
            start, end = block_index, block_index + len(block["text"]) + 1
            if block["type"] == "heading":
                style_requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": {"namedStyleType": "HEADING_2"},
                        "fields": "namedStyleType",
                    }
                })
            elif block["type"] == "bullet":
                style_requests.append({
                    "createParagraphBullets": {
                        "range": {"startIndex": start, "endIndex": end},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                })
            block_index = end
        index += len(text)

    for page_number, page in enumerate(pages):
        blocks = _parse_translated_blocks(str(page.get("text") or "")[:remaining_chars])
        remaining_chars -= sum(len(b["text"]) + 1 for b in blocks)
        page_images = images_by_page.get(page_number, [])
        used = [False] * len(page_images)

        for block in blocks:
            _insert_text_blocks([block])

            block_key = _no_marker_key(block["text"])
            if block_key is None:
                continue
            for i, image in enumerate(page_images):
                if not used[i] and _no_marker_key(image.get("reference_marker")) == block_key:
                    _insert_image(image)
                    used[i] = True

        # Diagrams that never matched a "NO.X" step marker (general product
        # photos, overview illustrations, unlabeled part diagrams) still
        # need to end up somewhere rather than being silently dropped.
        for i, image in enumerate(page_images):
            if not used[i]:
                _insert_image(image)

    if requests:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
    if style_requests:
        docs.documents().batchUpdate(documentId=doc_id, body={"requests": style_requests}).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"


def get_pdf_translations_folder_url() -> str:
    drive = drive_service()
    history_folder_id = _get_history_folder_id(drive)
    folder_id = _get_pdf_translations_folder_id(drive, history_folder_id)
    return f"https://drive.google.com/drive/folders/{folder_id}"


def list_pdf_translation_history() -> list[dict[str, str]]:
    """List translated-PDF docs, newest first — same shape as
    list_history_docs, but scoped to the "PDF Translations" subfolder so it
    doesn't mix in Instruction Manual docs."""
    drive = drive_service()
    history_folder_id = _get_history_folder_id(drive)
    folder_id = _get_pdf_translations_folder_id(drive, history_folder_id)

    results = drive.files().list(
        q=(
            f"'{folder_id}' in parents and trashed = false "
            "and mimeType = 'application/vnd.google-apps.document'"
        ),
        fields="files(id, name, webViewLink, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()

    return [
        {
            "id": f["id"],
            "name": f["name"],
            "url": f.get("webViewLink") or f"https://docs.google.com/document/d/{f['id']}/edit",
            "modified_at": f.get("modifiedTime"),
        }
        for f in results.get("files", [])
    ]


def get_history_folder_url() -> str:
    drive = drive_service()
    folder_id = _get_history_folder_id(drive)
    return f"https://drive.google.com/drive/folders/{folder_id}"


def get_images_folder_url() -> str:
    drive = drive_service()
    history_folder_id = _get_history_folder_id(drive)
    images_folder_id = _get_images_folder_id(drive, history_folder_id)
    return f"https://drive.google.com/drive/folders/{images_folder_id}"


def list_history_docs() -> list[dict[str, str]]:
    drive = drive_service()
    folder_id = _get_history_folder_id(drive)

    results = drive.files().list(
        q=(
            f"'{folder_id}' in parents and trashed = false "
            "and mimeType = 'application/vnd.google-apps.document'"
        ),
        fields="files(id, name, webViewLink, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=100,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora="allDrives",
    ).execute()

    return [
        {
            "id": f["id"],
            "name": f["name"],
            "url": f.get("webViewLink") or f"https://docs.google.com/document/d/{f['id']}/edit",
            "modified_at": f.get("modifiedTime"),
        }
        for f in results.get("files", [])
    ]


def trash_history_doc(file_id: str) -> None:
    drive = drive_service()
    drive.files().update(
        fileId=file_id,
        body={"trashed": True},
        supportsAllDrives=True,
    ).execute()


def _download(uri: str) -> bytes | None:
    try:
        request = urllib.request.Request(uri, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read()
    except Exception:
        return None


_template_placeholder_hashes: set[str] | None = None
_GAMBAR_PRODUK_HEADING = "gambar produk"


def _get_template_placeholder_hashes() -> set[str]:
    """Hash only the real "Gambar Produk" placeholder image(s) in the
    template — NOT every inline image in the doc. The template also has small
    decorative images elsewhere (a title accent bar, a "Saran Penggunaan"
    section divider) that must never be swapped for the product photo, so
    this locates the "Gambar Produk" heading first and only hashes images
    that physically appear after it."""
    global _template_placeholder_hashes
    if _template_placeholder_hashes is not None:
        return _template_placeholder_hashes

    docs = docs_service()
    doc = docs.documents().get(documentId=TEMPLATE_DOC_ID).execute()
    inline_objects = doc.get("inlineObjects", {})

    placeholder_object_ids: set[str] = set()
    past_heading = False
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        text = "".join(
            e.get("textRun", {}).get("content", "") for e in paragraph.get("elements", [])
        )
        is_heading = paragraph.get("paragraphStyle", {}).get("namedStyleType", "").startswith("HEADING")
        if is_heading and _GAMBAR_PRODUK_HEADING in text.strip().lower():
            past_heading = True
            continue
        if not past_heading:
            continue
        for el in paragraph.get("elements", []):
            image_el = el.get("inlineObjectElement")
            if image_el:
                placeholder_object_ids.add(image_el["inlineObjectId"])

    hashes: set[str] = set()
    for object_id in placeholder_object_ids:
        uri = (
            inline_objects.get(object_id, {})
            .get("inlineObjectProperties", {})
            .get("embeddedObject", {})
            .get("imageProperties", {})
            .get("contentUri")
        )
        if not uri:
            continue
        content = _download(uri)
        if content:
            hashes.add(hashlib.sha256(content).hexdigest())

    _template_placeholder_hashes = hashes
    return hashes


def find_product_photo_bytes(product_name: str) -> bytes | None:
    """Look for a real product photo already pasted into that product's generated
    Instruction Manual doc (someone did this by hand). Returns None if no manual we
    can find, or if the only images present are still the template's placeholders."""
    target_title = f"Instruction Manual - {product_name}"
    matching_doc = next(
        (d for d in list_history_docs() if d["name"] == target_title), None
    )
    if matching_doc is None:
        return None

    placeholder_hashes = _get_template_placeholder_hashes()

    docs = docs_service()
    doc = docs.documents().get(documentId=matching_doc["id"]).execute()
    for obj in doc.get("inlineObjects", {}).values():
        uri = (
            obj.get("inlineObjectProperties", {})
            .get("embeddedObject", {})
            .get("imageProperties", {})
            .get("contentUri")
        )
        if not uri:
            continue
        content = _download(uri)
        if not content:
            continue
        if hashlib.sha256(content).hexdigest() in placeholder_hashes:
            continue
        return content

    return None
