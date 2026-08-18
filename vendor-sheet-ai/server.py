from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from adapters.docs import (
    create_translated_pdf_doc,
    fetch_marketing_picture_bytes,
    find_product_photo_bytes,
    generate_description_doc,
    generate_instruction_manual_doc,
    get_description_history_folder_url,
    get_history_folder_url,
    get_images_folder_url,
    get_pdf_translations_folder_url,
    list_description_history_docs,
    list_history_docs,
    list_pdf_translation_history,
    trash_history_doc,
)
from adapters.gallery import (
    CARD_TYPES,
    COLOR_PALETTES,
    DEFAULT_FRAMING,
    DEFAULT_PALETTE,
    FRAMING_OPTIONS,
    chat_images_root,
    compose_keypoint_card,
    compose_spec_card,
    compose_usage_card,
    delete_gallery_card as remove_gallery_card_file,
    gallery_root,
    generate_ai_designed_keunggulan_card,
    generate_ai_designed_keypoint_card,
    generate_ai_designed_spec_card,
    generate_ai_designed_usage_card,
    generate_background_image,
    generate_keunggulan_content,
    generate_keypoint_icon,
    generate_keypoints,
    generate_product_scene,
    generate_spec_data,
    generate_usage_data,
    generate_usage_step_photo,
    refine_gallery_card,
    get_cutout_photo,
    hex_to_rgb,
    latest_gallery_card_url,
    list_gallery_cards,
    photo_path,
    photo_url_path,
    read_photo_meta,
    remove_card_frame,
    save_chat_image,
    save_gallery_card,
    save_source_photo,
)
from adapters.llm import answer_question, edit_image, generate_image
from adapters.pdf_translate import SUPPORTED_EXTENSIONS, translate_document_to_indonesian
from adapters.sheets import SheetFetchError
from config import settings
from core.prompts import FONT_THEME_OPTIONS, build_chat_prompt, select_relevant_rows
from services.pipeline import (
    fetch_product_detail,
    process_file,
    process_google_sheet,
    resync_linked_sheets,
)
from storage.state import StateStore

logger = logging.getLogger(__name__)

app = FastAPI(title="Vendor Sheet AI")


async def _sheet_sync_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(resync_linked_sheets)
        except Exception:
            logger.exception("Periodic sheet resync failed")
        await asyncio.sleep(settings.sheet_sync_interval_seconds)


@app.on_event("startup")
async def _start_sheet_sync() -> None:
    asyncio.create_task(_sheet_sync_loop())

app.mount("/gallery-assets", StaticFiles(directory=str(gallery_root())), name="gallery-assets")
app.mount("/chat-assets", StaticFiles(directory=str(chat_images_root())), name="chat-assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5180", "http://127.0.0.1:5180",
    ],
    allow_origin_regex=r"http://(192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+):(5173|5174|5180)",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_messages(result) -> list[dict]:
    messages: list[dict] = [
        {
            "role": "user",
            "type": "text",
            "text": f"Process vendor sheet \"{result.file_name}\".",
        }
    ]

    error_issues = [i for i in result.issues if i.severity == "error"]
    warning_issues = [i for i in result.issues if i.severity != "error"]

    intro = f"Processed {len(result.normalized_rows)} row(s) from {result.file_name}."
    if error_issues:
        intro += f" Found {len(error_issues)} error(s) that need attention."
    elif warning_issues:
        intro += f" Found {len(warning_issues)} warning(s) worth a look."
    else:
        intro += " No validation issues."

    messages.append({"role": "assistant", "type": "text", "text": intro})

    if result.issues:
        messages.append(
            {
                "role": "assistant",
                "type": "issues",
                "issues": [
                    {"field": i.field, "message": i.message, "severity": i.severity}
                    for i in result.issues
                ],
            }
        )

    for row in result.normalized_rows:
        messages.append({"role": "assistant", "type": "row", "row": row})

    return messages


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/history")
def history() -> dict:
    return {"processed_files": StateStore().list_processed_files()}


@app.post("/api/conversations")
def create_conversation() -> dict:
    return StateStore().create_conversation()


@app.get("/api/conversations")
def get_conversations(archived: bool = False) -> dict:
    return {"conversations": StateStore().list_conversations(archived=archived)}


class ConversationUpdate(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


@app.patch("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: int, payload: ConversationUpdate) -> dict:
    try:
        return StateStore().update_conversation(
            conversation_id,
            title=payload.title,
            pinned=payload.pinned,
            archived=payload.archived,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int) -> dict:
    StateStore().delete_conversation(conversation_id)
    return {"status": "ok"}


@app.get("/api/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: int) -> dict:
    return {"messages": StateStore().list_messages(conversation_id)}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...), conversation_id: int = Form(...)) -> dict:
    safe_filename = Path(file.filename or "").name
    if not safe_filename or not safe_filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / safe_filename
        with tmp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        try:
            result = process_file(tmp_path)
        except Exception as exc:
            logger.exception("Failed to process uploaded file %s", safe_filename)
            raise HTTPException(status_code=422, detail="Failed to process file") from exc

    messages = _build_messages(result)
    store = StateStore()
    store.set_initial_title(conversation_id, result.file_name)
    store.append_messages(conversation_id, messages)

    return {
        "file_name": result.file_name,
        "status": result.status,
        "messages": messages,
    }


class ChatRequest(BaseModel):
    message: str
    conversation_id: int


def _wants_description_doc(message: str) -> bool:
    text = message.lower()
    doc_terms = ("google doc", "google docs", "gdoc", "doc ", "docs", "dokumen", "document")
    description_terms = ("description", "deskripsi", "listing", "copywriting", "copy", "shopee", "tokopedia")
    return any(term in text for term in doc_terms) and any(term in text for term in description_terms)


def _wants_instruction_doc(message: str) -> bool:
    text = message.lower()
    doc_terms = ("google doc", "google docs", "gdoc", "doc ", "docs", "dokumen", "document")
    manual_terms = ("instruction", "manual", "instruksi", "petunjuk")
    return any(term in text for term in doc_terms) and any(term in text for term in manual_terms)


def _wants_unspecified_doc(message: str) -> bool:
    text = message.lower()
    doc_terms = ("google doc", "google docs", "gdoc", "doc ", "docs", "dokumen", "document")
    typed_terms = (
        "description", "deskripsi", "listing", "copywriting", "copy", "shopee", "tokopedia",
        "instruction", "manual", "instruksi", "petunjuk",
    )
    return any(term in text for term in doc_terms) and not any(term in text for term in typed_terms)


def _wants_doc_from_previous_template(message: str) -> bool:
    text = message.lower()
    doc_terms = (
        "google doc", "google docs", "gdoc", "doc", "docs", "dokumen", "document",
    )
    previous_terms = ("hasil", "ini", "itu", "tadi", "template", "building", "chat")
    manual_terms = ("instruction", "manual", "instruksi", "petunjuk")
    return (
        any(term in text for term in doc_terms)
        and any(term in text for term in previous_terms)
        and not any(term in text for term in manual_terms)
    )


def _infer_description_brand(row: dict) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("product_name", "vendor_name", "brand")).lower()
    if "safety" in text or "safetybro" in text or "safety bro" in text:
        return "safety_bro"
    if "gosave" in text:
        return "gosave"
    if "goto" in text:
        return "goto"
    return "goto"


def _extract_template_product_name(template_text: str) -> str | None:
    for line in template_text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().upper() == "NAMA_PRODUK":
            product_name = value.strip()
            return product_name or None
    return None


def _latest_description_template(conversation_id: int) -> str | None:
    messages = StateStore().list_messages(conversation_id)
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        text = str(message.get("text") or "").strip()
        if text.startswith("DESCRIPTION_TEMPLATE"):
            return text
    return None


def _find_row_by_product_name(product_name: str) -> dict | None:
    target = " ".join(product_name.lower().split())
    rows = StateStore().get_all_rows()
    for row in rows:
        row_name = " ".join(str(row.get("product_name") or "").lower().split())
        if row_name == target:
            return row
    for row in rows:
        row_name = " ".join(str(row.get("product_name") or "").lower().split())
        if row_name and (target in row_name or row_name in target):
            return row
    return None


def _build_doc_from_previous_template_message(conversation_id: int, message: str) -> dict | None:
    if not _wants_doc_from_previous_template(message):
        return None

    template_text = _latest_description_template(conversation_id)
    if not template_text:
        return {
            "role": "assistant",
            "type": "text",
            "text": "Belum ada hasil description building di chat ini. Minta dulu template description building untuk produknya, nanti bisa langsung aku jadikan Google Doc.",
        }

    product_name = _extract_template_product_name(template_text)
    if not product_name:
        return {
            "role": "assistant",
            "type": "text",
            "text": "Aku menemukan template di chat, tapi nama produknya belum kebaca. Coba sebutkan nama produknya saat minta dibuatkan Google Doc.",
        }

    row = _find_row_by_product_name(product_name)
    if not row:
        return {
            "role": "assistant",
            "type": "text",
            "text": f"Aku menemukan template untuk {product_name}, tapi produk itu belum ketemu di sheet. Sebutkan nama produk yang sesuai di sheet ya.",
        }

    brand = _infer_description_brand(row)
    detail_text = fetch_product_detail(row["detail_link"]) if row.get("detail_link") else None
    doc_url = generate_description_doc(row, brand, detail_text, template_text=template_text)

    return {
        "role": "assistant",
        "type": "description_doc",
        "text": template_text,
        "doc_url": doc_url,
        "doc_title": f"Google Doc dari hasil template siap: {product_name}",
        "doc_label": "Buka Google Doc",
        "doc_meta": f"Template description {brand.replace('_', ' ').upper()}",
    }


def _build_description_doc_message(message: str) -> dict | None:
    if not _wants_description_doc(message):
        return None

    rows = StateStore().get_all_rows()
    selected, _ = select_relevant_rows(message, rows)
    if not selected:
        return {
            "role": "assistant",
            "type": "text",
            "text": "Aku belum menemukan produk yang cocok dari sheet. Sebutkan nama produk yang mau dibuatkan Google Doc deskripsinya.",
        }

    row = selected[0]
    product_name = str(row.get("product_name") or "Produk").strip()
    brand = _infer_description_brand(row)
    detail_text = fetch_product_detail(row["detail_link"]) if row.get("detail_link") else None
    doc_url = generate_description_doc(row, brand, detail_text)

    return {
        "role": "assistant",
        "type": "doc_link",
        "title": f"Google Doc deskripsi siap: {product_name}",
        "url": doc_url,
        "label": "Buka Google Doc",
        "meta": f"Template description {brand.replace('_', ' ').upper()}",
    }


def _build_description_template_with_doc_message(message: str) -> dict | None:
    text = message.lower()
    description_terms = ("description", "deskripsi", "listing", "copywriting", "copy", "shopee", "tokopedia")
    building_terms = ("building", "template", "buatkan", "bikin", "generate")
    if not (any(term in text for term in description_terms) and any(term in text for term in building_terms)):
        return None

    rows = StateStore().get_all_rows()
    selected, _ = select_relevant_rows(message, rows)
    if not selected:
        return {
            "role": "assistant",
            "type": "text",
            "text": "Aku belum menemukan produk yang cocok dari sheet. Sebutkan nama produk yang mau dibuatkan description building-nya.",
        }

    row = selected[0]
    brand = _infer_description_brand(row)
    detail_text = fetch_product_detail(row["detail_link"]) if row.get("detail_link") else None
    template_text = _answer_chat_message(message)
    doc_url = generate_description_doc(row, brand, detail_text, template_text=template_text)

    return {
        "role": "assistant",
        "type": "description_doc",
        "text": template_text,
        "doc_url": doc_url,
        "doc_title": f"Google Doc deskripsi siap: {str(row.get('product_name') or 'Produk').strip()}",
        "doc_label": "Buka Google Doc",
        "doc_meta": f"Template description {brand.replace('_', ' ').upper()}",
    }


def _build_instruction_doc_message(message: str) -> dict | None:
    if not _wants_instruction_doc(message):
        return None

    rows = StateStore().get_all_rows()
    selected, _ = select_relevant_rows(message, rows)
    if not selected:
        return {
            "role": "assistant",
            "type": "text",
            "text": "Aku belum menemukan produk yang cocok dari sheet. Sebutkan nama produk yang mau dibuatkan Google Doc instruction manual-nya.",
        }

    row = selected[0]
    product_name = str(row.get("product_name") or "Produk").strip()
    detail_text = fetch_product_detail(row["detail_link"]) if row.get("detail_link") else None
    doc_url = generate_instruction_manual_doc(row, detail_text, image_count=1, sections=None)

    return {
        "role": "assistant",
        "type": "doc_link",
        "title": f"Google Doc instruction manual siap: {product_name}",
        "url": doc_url,
        "label": "Buka Google Doc",
        "meta": "Template instruction manual",
    }


def _build_doc_choice_message(message: str) -> dict | None:
    if not _wants_unspecified_doc(message):
        return None

    rows = StateStore().get_all_rows()
    selected, _ = select_relevant_rows(message, rows)
    product_name = str(selected[0].get("product_name") or "").strip() if selected else ""
    suffix = f" untuk {product_name}" if product_name else ""

    return {
        "role": "assistant",
        "type": "doc_choice",
        "title": "Pilih jenis Google Doc",
        "text": "Mau dibuatkan dokumen yang mana?",
        "options": [
            {
                "label": "Description",
                "prompt": f"Buatkan Google Doc description{suffix}",
                "description": "Template deskripsi marketplace.",
            },
            {
                "label": "Instruction Manual",
                "prompt": f"Buatkan Google Doc instruction manual{suffix}",
                "description": "Template panduan penggunaan produk.",
            },
        ],
    }


def _answer_chat_message(message: str) -> str:
    rows = StateStore().get_all_rows()
    selected, is_full_detail = select_relevant_rows(message, rows)

    if is_full_detail:
        rows_with_links = [row for row in selected if row.get("detail_link")]
        if rows_with_links:
            with ThreadPoolExecutor(max_workers=8) as executor:
                details = executor.map(
                    lambda row: fetch_product_detail(row["detail_link"]), rows_with_links
                )
            for row, detail in zip(rows_with_links, details):
                row["product_detail"] = detail

    prompt = build_chat_prompt(message, selected)
    return answer_question(prompt)


@app.post("/api/chat")
def chat(payload: ChatRequest) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        assistant_message = (
            _build_doc_from_previous_template_message(payload.conversation_id, message)
            or _build_doc_choice_message(message)
            or _build_description_template_with_doc_message(message)
            or _build_description_doc_message(message)
            or _build_instruction_doc_message(message)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to generate description doc from chat")
        raise HTTPException(status_code=500, detail="Failed to generate Google Doc") from exc

    if assistant_message is None:
        answer = _answer_chat_message(message)
        assistant_message = {"role": "assistant", "type": "text", "text": answer}

    store = StateStore()
    store.set_initial_title(payload.conversation_id, message)
    store.append_messages(
        payload.conversation_id,
        [
            {"role": "user", "type": "text", "text": message},
            assistant_message,
        ],
    )

    return {"answer": assistant_message.get("text") or assistant_message.get("url") or "", "message": assistant_message}


class EditMessageRequest(BaseModel):
    message: str


@app.patch("/api/conversations/{conversation_id}/messages/{message_id}")
def edit_message(conversation_id: int, message_id: int, payload: EditMessageRequest) -> dict:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    store = StateStore()
    try:
        store.update_message_and_delete_after(
            conversation_id,
            message_id,
            {"role": "user", "type": "text", "text": message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    answer = _answer_chat_message(message)
    store.append_messages(
        conversation_id,
        [{"role": "assistant", "type": "text", "text": answer}],
    )

    return {"messages": store.list_messages(conversation_id)}


_UNTITLED_PRODUCT_NAMES = {"", "-", "untitled", "untitled product", "(untitled row)", "untitled row"}


def _first_word(text: str) -> str:
    words = text.split()
    return words[0] if words else text


@app.get("/api/products")
def list_products() -> dict:
    rows = StateStore().get_all_rows()
    seen: set[str] = set()
    products: list[dict[str, str]] = []
    for row in rows:
        name = " ".join(str(row.get("product_name") or "").split())
        key = name.lower()
        if key in _UNTITLED_PRODUCT_NAMES or key in seen:
            continue
        seen.add(key)
        vendor = str(row.get("vendor_name") or "").strip()
        photo_url = photo_url_path(name) if photo_path(name).exists() else None
        products.append({"product_name": name, "vendor_name": _first_word(vendor), "photo_url": photo_url})
    return {"products": products}


class GenerateDocRequest(BaseModel):
    product_name: str
    image_count: int = 1
    sections: dict[str, bool] | None = None


@app.post("/api/products/generate-doc")
def generate_doc(payload: GenerateDocRequest) -> dict:
    if payload.image_count not in (1, 3):
        raise HTTPException(status_code=422, detail="image_count must be 1 or 3")

    rows = StateStore().get_all_rows()
    row = next((r for r in rows if r.get("product_name") == payload.product_name), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Product '{payload.product_name}' not found")

    detail_text = None
    if row.get("detail_link"):
        detail_text = fetch_product_detail(row["detail_link"])

    try:
        doc_url = generate_instruction_manual_doc(
            row,
            detail_text,
            image_count=payload.image_count,
            sections=payload.sections,
        )
        folder_url = get_history_folder_url()
        images_folder_url = get_images_folder_url()
    except Exception as exc:
        logger.exception("Failed to generate instruction manual for %s", payload.product_name)
        raise HTTPException(status_code=500, detail="Failed to generate document") from exc

    return {"doc_url": doc_url, "folder_url": folder_url, "images_folder_url": images_folder_url}


class GenerateDescriptionRequest(BaseModel):
    product_name: str
    brand: str


@app.post("/api/products/generate-description")
def generate_description(payload: GenerateDescriptionRequest) -> dict:
    rows = StateStore().get_all_rows()
    row = next((r for r in rows if r.get("product_name") == payload.product_name), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Product '{payload.product_name}' not found")

    detail_text = None
    if row.get("detail_link"):
        detail_text = fetch_product_detail(row["detail_link"])

    try:
        doc_url = generate_description_doc(row, payload.brand, detail_text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to generate description for %s", payload.product_name)
        raise HTTPException(status_code=500, detail="Failed to generate document") from exc

    return {"doc_url": doc_url}


@app.get("/api/products/description-history")
def description_history() -> dict:
    try:
        docs = list_description_history_docs()
        folder_url = get_description_history_folder_url()
    except Exception as exc:
        logger.exception("Failed to load description history")
        raise HTTPException(status_code=500, detail="Failed to load history") from exc

    return {"docs": docs, "folder_url": folder_url}


@app.delete("/api/products/description-history/{file_id}")
def delete_description_history_item(file_id: str) -> dict:
    try:
        trash_history_doc(file_id)
    except Exception as exc:
        logger.exception("Failed to delete description history item %s", file_id)
        raise HTTPException(status_code=500, detail="Failed to delete document") from exc

    return {"status": "ok"}


@app.get("/api/products/doc-history")
def doc_history() -> dict:
    try:
        docs = list_history_docs()
        folder_url = get_history_folder_url()
        images_folder_url = get_images_folder_url()
    except Exception as exc:
        logger.exception("Failed to load instruction manual history")
        raise HTTPException(status_code=500, detail="Failed to load history") from exc

    return {"docs": docs, "folder_url": folder_url, "images_folder_url": images_folder_url}


@app.delete("/api/products/doc-history/{file_id}")
def delete_doc_history_item(file_id: str) -> dict:
    try:
        trash_history_doc(file_id)
    except Exception as exc:
        logger.exception("Failed to delete history document %s", file_id)
        raise HTTPException(status_code=500, detail="Failed to delete document") from exc

    return {"status": "ok"}


@app.post("/api/pdf/translate")
async def translate_pdf(file: UploadFile = File(...)) -> dict:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Upload a PDF, an image (JPG/PNG/WEBP/BMP/GIF), or a Word .docx file.",
        )

    content = await file.read()
    title = f"Translation - {Path(file.filename).stem}"

    try:
        pages = await asyncio.to_thread(translate_document_to_indonesian, content, file.filename)
        doc_url = await asyncio.to_thread(create_translated_pdf_doc, title, pages)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to translate document %s", file.filename)
        raise HTTPException(status_code=500, detail="Failed to translate document") from exc

    return {"doc_url": doc_url}


@app.get("/api/pdf/translate-history")
def pdf_translate_history() -> dict:
    try:
        docs = list_pdf_translation_history()
        folder_url = get_pdf_translations_folder_url()
    except Exception as exc:
        logger.exception("Failed to load PDF translation history")
        raise HTTPException(status_code=500, detail="Failed to load history") from exc

    return {"docs": docs, "folder_url": folder_url}


@app.delete("/api/pdf/translate-history/{file_id}")
def delete_pdf_translation_history_item(file_id: str) -> dict:
    try:
        trash_history_doc(file_id)
    except Exception as exc:
        logger.exception("Failed to delete PDF translation history item %s", file_id)
        raise HTTPException(status_code=500, detail="Failed to delete document") from exc

    return {"status": "ok"}


class SheetRequest(BaseModel):
    url: str
    conversation_id: int


@app.post("/api/sheets/process")
def process_sheet(payload: SheetRequest) -> dict:
    try:
        result = process_google_sheet(payload.url)
    except SheetFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to process Google Sheet %s", payload.url)
        raise HTTPException(status_code=422, detail="Failed to process sheet") from exc

    messages = _build_messages(result)
    store = StateStore()
    store.set_initial_title(payload.conversation_id, result.file_name)
    store.append_messages(payload.conversation_id, messages)

    return {
        "file_name": result.file_name,
        "status": result.status,
        "messages": messages,
    }


def _normalize_product_name(name: str) -> str:
    """Collapse runs of whitespace the same way /api/products does when it
    builds the list the frontend actually selects from — otherwise a sheet
    name with a stray double space (or tab) never matches the name the
    frontend sends back, even though it's "the same" product to a human."""
    return " ".join(str(name or "").split())


def _find_product_row(product_name: str) -> dict:
    target = _normalize_product_name(product_name)
    rows = StateStore().get_all_rows()
    row = next((r for r in rows if _normalize_product_name(r.get("product_name")) == target), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_name}' not found")
    return row


def _find_product_row_or_none(product_name: str) -> dict | None:
    target = _normalize_product_name(product_name)
    rows = StateStore().get_all_rows()
    return next((r for r in rows if _normalize_product_name(r.get("product_name")) == target), None)


def _sync_photo_from_sheet(product_name: str, picture_url: str) -> bool:
    try:
        image_bytes = fetch_marketing_picture_bytes(picture_url)
    except Exception:
        logger.exception("Failed to fetch marketing picture from sheet for %s", product_name)
        return False
    if not image_bytes:
        logger.warning("Could not resolve a usable image for %s from %s", product_name, picture_url)
        return False
    save_source_photo(product_name, image_bytes, source="sheet", source_url=picture_url)
    return True


@app.get("/api/gallery/{product_name}")
def gallery_status(product_name: str) -> dict:
    has_photo = photo_path(product_name).exists()
    photo_meta = read_photo_meta(product_name) if has_photo else None
    photo_source = photo_meta.get("source") if photo_meta else ("uploaded" if has_photo else None)

    row = _find_product_row_or_none(product_name)
    sheet_picture_url = row.get("marketing_picture_link") if row else None

    if has_photo and photo_source == "sheet" and sheet_picture_url:
        # The photo we have on disk was itself pulled from the sheet last
        # time — if that link has since changed (someone swapped the photo
        # in the sheet), silently re-pull instead of forever serving the
        # stale one. A manually uploaded photo (photo_source == "uploaded")
        # is never touched here — that was a deliberate override.
        if photo_meta.get("source_url") != sheet_picture_url:
            if _sync_photo_from_sheet(product_name, sheet_picture_url):
                photo_source = "sheet"

    if not has_photo:
        try:
            found = find_product_photo_bytes(product_name)
        except Exception:
            logger.exception("Failed to look up instruction manual photo for %s", product_name)
            found = None
        if found:
            save_source_photo(product_name, found, source="instruction_manual")
            has_photo = True
            photo_source = "instruction_manual"

    if not has_photo and sheet_picture_url:
        if _sync_photo_from_sheet(product_name, sheet_picture_url):
            has_photo = True
            photo_source = "sheet"

    history = list_gallery_cards(product_name)
    cards = {}
    for card_type in CARD_TYPES:
        type_history = [item for item in history if item["card_type"] == card_type]
        cards[card_type] = {
            "has_card": bool(type_history),
            "card_url": type_history[0]["url"] if type_history else None,
        }

    return {
        "has_photo": has_photo,
        "photo_source": photo_source,
        "photo_url": photo_url_path(product_name) if has_photo else None,
        "has_sheet_photo_link": bool(sheet_picture_url),
        "cards": cards,
        "card_history": history,
    }


@app.post("/api/gallery/{product_name}/refresh-photo")
def refresh_gallery_photo(product_name: str) -> dict:
    """Force re-pull the product photo from its sheet link right now, even if
    the link text hasn't changed (the file behind a Drive link can be
    swapped without the link itself changing) and even if the current photo
    was manually uploaded — this one is an explicit user action, unlike the
    silent best-effort sync in gallery_status."""
    row = _find_product_row_or_none(product_name)
    picture_url = row.get("marketing_picture_link") if row else None
    if not picture_url:
        raise HTTPException(status_code=404, detail="Produk ini belum punya link foto di sheet")

    if not _sync_photo_from_sheet(product_name, picture_url):
        raise HTTPException(status_code=502, detail="Gagal mengambil foto dari link sheet")

    return {"ok": True, "photo_url": photo_url_path(product_name), "photo_source": "sheet"}


@app.get("/api/gallery-history")
def gallery_history() -> dict:
    rows = StateStore().get_all_rows()
    items = []
    for row in rows:
        product_name = row.get("product_name")
        if not product_name:
            continue
        for card in list_gallery_cards(product_name):
            items.append({
                **card,
                "product_name": product_name,
                "vendor_name": row.get("vendor_name") or "",
            })

    items.sort(key=lambda item: item["generated_at"], reverse=True)
    return {"items": items}


@app.delete("/api/gallery/{product_name}/cards/{filename}")
def delete_gallery_card_route(product_name: str, filename: str) -> dict:
    try:
        remove_gallery_card_file(product_name, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Image history not found") from exc
    return {"ok": True, "card_history": list_gallery_cards(product_name)}


@app.post("/api/gallery/{product_name}/cards/{filename}/remove-frame")
def remove_gallery_card_frame_route(product_name: str, filename: str) -> dict:
    try:
        new_path = remove_card_frame(product_name, filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Image history not found") from exc
    except Exception as exc:
        logger.exception("Frame removal failed for %s/%s", product_name, filename)
        raise HTTPException(status_code=500, detail="Gagal menghapus frame, coba lagi") from exc
    safe_name = Path(new_path).parent.parent.name
    return {
        "ok": True,
        "url": f"/gallery-assets/{safe_name}/cards/{new_path.name}",
        "card_history": list_gallery_cards(product_name),
    }


@app.post("/api/gallery/{product_name}/cards/{filename}/refine")
def refine_gallery_card_route(
    product_name: str, filename: str, instruction: str = Form("")
) -> dict:
    try:
        new_path = refine_gallery_card(product_name, filename, instruction)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Image history not found") from exc
    except Exception as exc:
        logger.exception("Card refine failed for %s/%s", product_name, filename)
        raise HTTPException(status_code=500, detail="Gagal memperbaiki kartu, coba lagi") from exc
    safe_name = Path(new_path).parent.parent.name
    return {
        "ok": True,
        "url": f"/gallery-assets/{safe_name}/cards/{new_path.name}",
        "card_history": list_gallery_cards(product_name),
    }


@app.post("/api/image-chat/generate")
async def image_chat_generate(
    message: str = Form(...),
    product_name: str | None = Form(None),
    reference_url: str | None = Form(None),
    reference_file: UploadFile | None = File(None),
    conversation_id: int | None = Form(None),
) -> dict:
    """Free-form chat-style image generation/editing — no structured fields,
    just a text instruction each turn, like talking to ChatGPT/Gemini's image
    mode. Three ways a reference image can ground this turn (checked in this
    order): an uploaded file (user attached something fresh), a previous
    turn's own generated image (so "buat lebih terang" edits what's already
    on screen instead of generating something unrelated), or a product's
    real cutout photo (so the very first message in a conversation about a
    specific product stays grounded in its real appearance instead of the
    model inventing one). With no reference at all, it's a plain text-to-
    image generation.

    When conversation_id is given, this turn (the user's instruction +
    whichever reference was actually used, and the assistant's result) is
    persisted the same way sheet Q&A turns are — otherwise it only lives in
    the caller's own local state and disappears on reload."""
    if not message.strip():
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong")

    reference_bytes: bytes | None = None
    persisted_reference_url: str | None = None
    if reference_file is not None:
        reference_bytes = await reference_file.read()
    elif reference_url:
        # reference_url is one of our own /chat-assets/{filename}.png URLs
        # from an earlier turn — resolve it back to the file on disk rather
        # than trusting/fetching an arbitrary URL from the client.
        filename = Path(reference_url).name
        candidate = chat_images_root() / filename
        if candidate.exists():
            reference_bytes = candidate.read_bytes()
            persisted_reference_url = reference_url
    elif product_name:
        try:
            cutout = get_cutout_photo(product_name)
            buffer = io.BytesIO()
            flattened = Image.new("RGB", cutout.size, (255, 255, 255))
            flattened.paste(cutout, (0, 0), cutout)
            flattened.save(buffer, format="PNG")
            reference_bytes = buffer.getvalue()
        except Exception:
            logger.exception("Could not load product photo for image chat grounding: %s", product_name)

    try:
        if reference_bytes is not None:
            ref_image = Image.open(io.BytesIO(reference_bytes)).convert("RGB")
            result_bytes = edit_image(message, ref_image)
        else:
            result_bytes = generate_image(message)
    except Exception as exc:
        logger.exception("Image chat generation failed")
        raise HTTPException(status_code=500, detail="Gagal generate gambar, coba lagi") from exc

    image_url = save_chat_image(result_bytes)

    if conversation_id is not None:
        # A freshly-uploaded reference wasn't saved anywhere yet — save it now
        # so the user's turn has something to show after a reload too. A
        # reused previous-turn image (persisted_reference_url) and a product
        # cutout (no user attachment at all) don't need re-saving.
        if reference_file is not None and reference_bytes is not None:
            persisted_reference_url = save_chat_image(reference_bytes)

        store = StateStore()
        store.set_initial_title(conversation_id, message.strip())
        store.append_messages(
            conversation_id,
            [
                {
                    "role": "user",
                    "type": "image_gen",
                    "text": message.strip(),
                    "previews": [persisted_reference_url] if persisted_reference_url else [],
                },
                {
                    "role": "assistant",
                    "type": "image_gen",
                    "status": "done",
                    "images": [{"url": image_url}],
                },
            ],
        )

    return {"image_url": image_url}


@app.post("/api/gallery/{product_name}/photo")
async def upload_gallery_photo(product_name: str, file: UploadFile = File(...)) -> dict:
    content = await file.read()
    try:
        save_source_photo(product_name, content)
    except Exception as exc:
        logger.exception("Failed to save uploaded gallery photo for %s", product_name)
        raise HTTPException(status_code=400, detail="Invalid image file") from exc

    return {"photo_url": photo_url_path(product_name)}


@app.post("/api/gallery/{product_name}/generate")
def generate_gallery_card(
    product_name: str,
    ai_scene: bool = False,
    with_model: bool = False,
    keypoint: bool = True,
    spec: bool = True,
    usage: bool = True,
    keunggulan: bool = False,
    keunggulan_count: int = 3,
    font_theme: str | None = None,
    palette: str = DEFAULT_PALETTE,
    framing: str = DEFAULT_FRAMING,
    custom_scene: str | None = None,
    custom_primary: str | None = None,
    custom_accent: str | None = None,
    spec_manual: bool = False,
    spec_manual_text: str | None = None,
    keypoint_manual: bool = False,
    keypoint_manual_text: str | None = None,
    ai_full_design: bool = True,
    usage_full_design: bool = True,
    spec_full_design: bool = True,
    custom_prompt: str | None = None,
) -> dict:
    if not (keypoint or spec or usage or keunggulan):
        raise HTTPException(status_code=400, detail="Pilih minimal satu jenis kartu untuk di-generate")

    keunggulan_count = max(1, min(3, keunggulan_count))

    if palette not in COLOR_PALETTES:
        palette = DEFAULT_PALETTE

    if framing not in FRAMING_OPTIONS:
        framing = DEFAULT_FRAMING

    # No manual light/dark toggle anymore — the mood follows the brand's own
    # character instead: GOTO is cute/playful (bright), the other three lean
    # fierce/sharp safety-gear energy (dark, dramatic).
    dark_background = framing != "goto"

    # A manual font override must be one of the real theme names — anything
    # else (empty string, stale value) just means "let the AI decide", same
    # as before this option existed.
    manual_font_theme = font_theme if font_theme in FONT_THEME_OPTIONS else None
    custom_scene = (custom_scene or "").strip() or None
    custom_prompt = (custom_prompt or "").strip()

    # Custom hex colors only take effect when both are given and valid —
    # otherwise fall back to the selected palette (and, for the icon-gen
    # prompt below, the palette's own primary color).
    custom_primary_rgb = hex_to_rgb(custom_primary) if custom_primary else None
    custom_accent_rgb = hex_to_rgb(custom_accent) if custom_accent else None
    use_custom_colors = custom_primary_rgb is not None and custom_accent_rgb is not None
    if not use_custom_colors:
        custom_primary = None
        custom_accent = None

    row = _find_product_row(product_name)

    source_path = photo_path(product_name)
    if not source_path.exists():
        raise HTTPException(
            status_code=400,
            detail="No product photo yet — upload one or generate the instruction manual first",
        )

    try:
        photo = get_cutout_photo(product_name)

        # If the user typed their own scene (e.g. "di kelas", "di kantor"),
        # that text replaces the AI's own guess at where this product
        # belongs — used below to generate each card type's own background.
        keypoints_data = generate_keypoints(row, framing) if (keypoint or spec or usage) else None
        if keypoint_manual and keypoints_data is not None:
            # User typed the keypoint cells by hand — use exactly those (capped
            # at 3, same as the card's fixed 3 badge slots), nothing AI-guessed
            # mixed in. Tagline/background scene stay AI-derived either way.
            # Strips a leading bullet marker ("- ", "• ", "* ", "1. ") off each
            # line — people naturally paste keypoints as a bulleted/numbered
            # list, and that marker isn't part of the actual keypoint text, so
            # left in it rendered on the card as a stray "- " before every
            # badge label.
            manual_keypoints = [
                re.sub(r"^[-•*]\s+|^\d+[.)]\s+", "", line.strip())
                for line in (keypoint_manual_text or "").splitlines() if line.strip()
            ][:3]
            keypoints_data["keypoints"] = manual_keypoints
        scene_description = custom_scene or (keypoints_data["background_scene"] if keypoints_data else None)

        # Each card type gets its own independently AI-generated background
        # (a separate generate_product_scene / generate_background_image call
        # per card) instead of one shared shot reused everywhere — so a
        # product's keypoint/spec/usage cards each look like their own photo,
        # not 3 copies of the exact same background. Costs more API calls
        # than the old shared-shot approach, but that's the tradeoff for
        # each card in the set actually looking distinct.
        def _generate_card_scene(layout: str = "keypoint", force: bool = False):
            scene_photo = (
                generate_product_scene(
                    photo, product_name, scene_description, with_model, framing=framing, layout=layout,
                )
                if ai_scene or force else None
            )
            # background_photo is only ever actually used as the plain-boxed-photo
            # fallback (when full_scene_photo isn't requested, or its generation
            # failed) — skip paying for this AI call entirely when full_scene_photo
            # already came back, since compose_*_card ignores background_photo
            # whenever full_scene_photo is present.
            bg_photo = (
                generate_background_image(scene_description, framing=framing)
                if scene_description and scene_photo is None else None
            )
            return scene_photo, bg_photo

        if keypoint:
            logger.info(
                "Gallery keypoints for %s -> tagline=%r keypoints=%r background_scene=%r",
                product_name,
                keypoints_data["tagline"],
                keypoints_data["keypoints"],
                scene_description,
            )
            keypoint_bytes = None
            if ai_full_design:
                # The whole card (background, headline, badges, icons) drawn
                # by the image model in one shot instead of PIL compositing
                # — reads far more like an actual designed poster, at the
                # cost of the model occasionally misspelling a word since
                # it's drawing letterforms, not typesetting a string. Only
                # attempted when the user explicitly opted in (they've been
                # told to proofread the result); falls back to the
                # deterministic/typo-proof compose path on failure.
                ai_card = generate_ai_designed_keypoint_card(
                    photo, product_name, keypoints_data["tagline"], keypoints_data["keypoints"],
                    scene_description, palette=palette, framing=framing,
                    extra_instruction=custom_prompt,
                )
                if ai_card is not None:
                    buffer = io.BytesIO()
                    ai_card.convert("RGB").save(buffer, format="PNG")
                    keypoint_bytes = buffer.getvalue()

            if keypoint_bytes is None:
                resolved_font_theme = manual_font_theme or keypoints_data["font_theme"]
                primary_color = custom_primary_rgb or COLOR_PALETTES[palette]["primary"]
                keypoint_icons = [
                    generate_keypoint_icon(kp, primary_color, framing=framing) for kp in keypoints_data["keypoints"]
                ]
                full_scene_photo, background_photo = _generate_card_scene()

                keypoint_bytes = compose_keypoint_card(
                    product_name=product_name,
                    tagline=keypoints_data["tagline"],
                    keypoints=keypoints_data["keypoints"],
                    photo=photo,
                    background_photo=None if full_scene_photo is not None else background_photo,
                    keypoint_icons=keypoint_icons,
                    full_scene_photo=full_scene_photo,
                    font_theme=resolved_font_theme,
                    palette=palette,
                    dark_theme=dark_background,
                    custom_primary=custom_primary,
                    custom_accent=custom_accent,
                    framing=framing,
                )
            save_gallery_card(product_name, "keypoint", keypoint_bytes)

        if spec:
            if spec_manual:
                # User asked to fill this in by hand — render exactly what
                # they typed, nothing AI-generated mixed in.
                spec_data: dict[str, str] = {}
                manual_text = (spec_manual_text or "").strip()
                logger.info("Gallery spec for %s -> manual text %r", product_name, manual_text)
            else:
                # The sheet row alone is often too thin for a full spec block —
                # pull from the product's detail-link page too (same source
                # already used for the instruction manual) so fields like
                # UKURAN/MATERIAL/MADE IN aren't left as "-" just because the
                # sheet's own columns didn't have them.
                detail_text = fetch_product_detail(row["detail_link"]) if row.get("detail_link") else None
                spec_data = generate_spec_data(row, detail_text)
                manual_text = None
                logger.info("Gallery spec for %s -> %r", product_name, spec_data)

            spec_bytes = None
            if spec_full_design:
                # Same "whole card in one AI shot" idea as the keypoint/usage
                # full-design options — one call designs the hero photo,
                # title/tagline, spec rows (with their own icons), and the
                # bottom highlight bar together.
                manual_lines = (
                    [line.strip() for line in manual_text.splitlines() if line.strip()]
                    if spec_manual and manual_text else None
                )
                ai_spec_card = generate_ai_designed_spec_card(
                    photo, product_name, spec_data, keypoints_data["keypoints"], scene_description,
                    manual_lines=manual_lines, palette=palette, framing=framing,
                    extra_instruction=custom_prompt,
                )
                if ai_spec_card is not None:
                    buffer = io.BytesIO()
                    ai_spec_card.convert("RGB").save(buffer, format="PNG")
                    spec_bytes = buffer.getvalue()

            if spec_bytes is None:
                full_scene_photo, background_photo = _generate_card_scene()
                spec_bytes = compose_spec_card(
                    product_name=product_name, spec=spec_data, photo=photo,
                    background_photo=None if full_scene_photo is not None else background_photo,
                    full_scene_photo=full_scene_photo,
                    font_theme=manual_font_theme or keypoints_data["font_theme"],
                    palette=palette,
                    dark_theme=dark_background,
                    custom_primary=custom_primary,
                    custom_accent=custom_accent,
                    manual_text=manual_text,
                    framing=framing,
                )
            save_gallery_card(product_name, "spec", spec_bytes)

        if usage:
            usage_data = generate_usage_data(row, framing)
            usage_steps = usage_data["steps"]
            usage_subtitle = usage_data["subtitle"]
            logger.info("Gallery usage steps for %s -> %r", product_name, usage_data)

            usage_bytes = None
            if usage_full_design:
                # Same "whole card in one AI shot" idea as the keypoint
                # card's full-design option — one call designs the heading,
                # hero photo, and all step callouts together instead of
                # compositing a separately-generated photo per step, at the
                # same proofread-before-publish trade-off.
                ai_usage_card = generate_ai_designed_usage_card(
                    photo, product_name, usage_steps, scene_description,
                    subtitle=usage_subtitle, palette=palette, framing=framing,
                    extra_instruction=custom_prompt,
                )
                if ai_usage_card is not None:
                    buffer = io.BytesIO()
                    ai_usage_card.convert("RGB").save(buffer, format="PNG")
                    usage_bytes = buffer.getvalue()

            if usage_bytes is None:
                steps_with_images = [
                    {
                        "caption": step["caption"],
                        "desc": step["desc"],
                        "image": generate_usage_step_photo(photo, product_name, step["scene"], framing=framing),
                    }
                    for step in usage_steps
                ]
                full_scene_photo, background_photo = _generate_card_scene(layout="usage", force=True)
                usage_bytes = compose_usage_card(
                    product_name=product_name, photo=photo, steps=steps_with_images,
                    subtitle=usage_subtitle,
                    background_photo=None if full_scene_photo is not None else background_photo,
                    full_scene_photo=full_scene_photo,
                    font_theme=manual_font_theme or keypoints_data["font_theme"],
                    palette=palette,
                    dark_theme=dark_background,
                    custom_primary=custom_primary,
                    custom_accent=custom_accent,
                    framing=framing,
                )
            save_gallery_card(product_name, "usage", usage_bytes)

        if keunggulan:
            # Unlike keypoint/spec/usage (one fixed image slot each),
            # "keunggulan" produces however many the user asked for
            # (1-3) in one generate click — each its own distinct
            # advantage/headline/photo, not variations of the same card.
            keunggulan_items = generate_keunggulan_content(row, framing)[:keunggulan_count]
            logger.info(
                "Gallery keunggulan for %s -> %d item(s) %r",
                product_name, len(keunggulan_items), keunggulan_items,
            )
            for item in keunggulan_items:
                item_scene = custom_scene or item["scene"]
                keunggulan_card = generate_ai_designed_keunggulan_card(
                    photo, product_name, item["headline"], item["emphasis"], item["points"],
                    item_scene, palette=palette, framing=framing,
                    extra_instruction=custom_prompt,
                )
                if keunggulan_card is not None:
                    buffer = io.BytesIO()
                    keunggulan_card.convert("RGB").save(buffer, format="PNG")
                    save_gallery_card(product_name, "keunggulan", buffer.getvalue())
    except Exception as exc:
        logger.exception("Failed to generate gallery card for %s", product_name)
        raise HTTPException(status_code=500, detail="Failed to generate gallery card") from exc

    return {
        "cards": {
            card_type: latest_gallery_card_url(product_name, card_type) for card_type in CARD_TYPES
        },
        "card_history": list_gallery_cards(product_name),
    }
