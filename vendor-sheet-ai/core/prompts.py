from __future__ import annotations

import re

_STOPWORDS = {
    "apa", "yang", "dan", "untuk", "dari", "ini", "itu", "buatkan", "buat",
    "tolong", "please", "the", "for", "what", "is", "are", "spesifikasi",
    "spec", "specs", "specification", "specifications", "tentang", "soal",
    "dong", "dulu", "ada", "gimana", "bagaimana", "kasih", "coba", "detail",
    "details", "lengkap", "full", "semua",
}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def select_relevant_rows(
    question: str, rows: list[dict[str, object]], max_rows: int = 20
) -> tuple[list[dict[str, object]], bool]:
    """Return (rows_to_send, is_full_detail). When the database is small, send
    everything. Otherwise score rows by keyword overlap with the question and
    only send full detail for the matches, to keep the prompt a sane size."""
    if len(rows) <= max_rows:
        return rows, True

    tokens = _tokenize(question)
    if not tokens:
        return rows[:max_rows], False

    scored = []
    for row in rows:
        haystack = " ".join(str(v).lower() for v in row.values())
        score = sum(1 for t in tokens if t in haystack)
        if score > 0:
            scored.append((score, row))

    if not scored:
        return rows[:max_rows], False

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:max_rows]], True


SUMMARY_SYSTEM_INSTRUCTION = (
    "You are a packaging operations analyst. You read a single row from a vendor "
    "sheet (raw CSV data, may contain missing or messy fields) and produce a short, "
    "factual summary a production planner can scan in seconds. "
    "Never invent values that aren't present in the row. If a field is missing, say so "
    "briefly instead of guessing. Keep the summary to 2-3 sentences, plain text, no markdown."
)

_FIELD_LABELS: dict[str, str] = {
    "vendor_name": "Vendor",
    "product_name": "Product",
    "width": "Width",
    "height": "Height",
    "quantity": "Quantity",
    "material": "Material",
    "due_date": "Due date",
}


def _format_row_context(row: dict[str, object]) -> str:
    lines = []
    for key, value in row.items():
        if str(value).strip().lower() == "false":
            continue
        label = _FIELD_LABELS.get(key, key.replace("_", " ").title())
        display_value = str(value).strip() if value not in (None, "") else "(missing)"
        lines.append(f"- {label}: {display_value}")
    return "\n".join(lines) if lines else "- (no fields provided)"


def build_summary_prompt(row: dict[str, object]) -> str:
    vendor = str(row.get("vendor_name") or "Unknown vendor").strip()
    product = str(row.get("product_name") or "Unknown product").strip()

    return (
        f"{SUMMARY_SYSTEM_INSTRUCTION}\n\n"
        f"Row data for vendor \"{vendor}\", product \"{product}\":\n"
        f"{_format_row_context(row)}\n\n"
        "Write the summary now."
    )


CHAT_SYSTEM_INSTRUCTION = (
    "You are a packaging operations assistant. You answer questions about a "
    "vendor sheet database that has already been loaded below. Only use the data "
    "provided — never invent vendors, products, or measurements that aren't in it. "
    "If the answer isn't in the data, say so plainly and suggest what field might "
    "be missing. Match the level of detail to the question: for a quick factual "
    "question, answer in a sentence or two. But if the user asks for specifications, "
    "details, or a full breakdown of a product, respond with a complete, well-organized "
    "listing of every relevant field for that product (vendor, dimensions, quantity, "
    "material, due date, dieline, etc.), not just a one-line summary. Cite the product "
    "name when relevant. Write in plain text only — no markdown, no asterisks, no bold "
    "or italic formatting. Use plain dashes or numbers for lists and line breaks for "
    "structure instead."
)

CHAT_SYSTEM_INSTRUCTION += (
    "\n\nIf the user asks for marketplace description, product copy, description building, "
    "listing copy, Shopee/Tokopedia copy, or a ready-to-use selling description, answer "
    "with this exact template format and no markdown:\n"
    "DESCRIPTION_TEMPLATE\n"
    "NAMA_PRODUK: [product name]\n"
    "VENDOR: [vendor name if present]\n"
    "INTRO: [2-4 warm Bahasa Indonesia sentences grounded in the data]\n"
    "KEUNGGULAN:\n"
    "1. [benefit sentence]\n"
    "2. [benefit sentence]\n"
    "3. [benefit sentence]\n"
    "4. [benefit sentence]\n"
    "5. [benefit sentence]\n"
    "SPESIFIKASI:\n"
    "- [Label: value]\n"
    "- [Label: value]\n"
    "VARIAN:\n"
    "- [variant or product name]\n"
    "FAQ:\n"
    "1. [question]?\n"
    "- [answer].\n"
    "2. [question]?\n"
    "- [answer].\n"
    "3. [question]?\n"
    "- [answer]."
)


def build_chat_prompt(question: str, rows: list[dict[str, object]]) -> str:
    if not rows:
        rows_context = "(no rows stored yet)"
    else:
        selected, is_full_detail = select_relevant_rows(question, rows)

        if is_full_detail:
            blocks = []
            for i, row in enumerate(selected, start=1):
                visible = {k: v for k, v in row.items() if k not in ("source", "row_index")}
                blocks.append(f"Row {i}:\n{_format_row_context(visible)}")
            rows_context = "\n\n".join(blocks)
        else:
            names = [str(row.get("product_name", "(untitled)")) for row in selected]
            rows_context = (
                f"(The database has {len(rows)} rows — too many to list in full, and "
                "none matched keywords from the question, so only product names are "
                f"shown below. Ask the user to name a specific product.)\n"
                + "\n".join(f"- {name}" for name in names)
            )

    return (
        f"{CHAT_SYSTEM_INSTRUCTION}\n\n"
        f"--- Vendor sheet database ---\n{rows_context}\n--- end of database ---\n\n"
        f"Question: {question}\n"
        "Answer:"
    )


INSTRUCTION_MANUAL_FIELDS = [
    "MEREK", "TIPE", "ITEM_NAME", "NAMA_BARANG_DESKRIPSI", "DESKRIPSI_PRODUK",
    "FUNGSI_PRODUK", "SPEC_DETAILS", "SERTIFIKAT", "KAPASITAS", "MADE_IN",
    "ISI_KEMASAN", "VARIAN_PRODUK", "FITUR_1", "FITUR_2", "FITUR_3", "FITUR_4",
    "FITUR_5", "CARA_PENGGUNAAN", "PERAWATAN",
]

INSTRUCTION_MANUAL_SYSTEM_INSTRUCTION = (
    "You are a packaging operations writer producing content for a product instruction "
    "manual template (in Bahasa Indonesia). You are given raw vendor-sheet data for one "
    "product (and, if available, detailed variant specifications). Fill in the JSON fields "
    "below using ONLY information present in the data. Never invent certifications, "
    "capacities, materials, countries of origin, or other specifics that aren't in the data. "
    "If a field genuinely has no source data, write a short, honest placeholder like \"-\" or "
    "\"Tidak tersedia\" instead of guessing. Write in plain text, no markdown, no asterisks. "
    "SPEC_DETAILS and ISI_KEMASAN may contain multiple lines separated by \\n if there is "
    "more than one item. "
    "VARIAN_PRODUK must list EVERY variant present in the data (color, size, model, etc.) "
    "as separate lines separated by \\n — do not shorten, summarize, or drop any variant "
    "that's actually in the source data, no matter how many there are. The source data may have "
    "columns like \"VARIAN 1\", \"VARIAN 2\", \"VARIAN 3\" whose raw values are individual "
    "entries jammed together with NO space or separator at all — e.g. "
    "\"size 39size 40size 41size 42size 43\" means five separate entries (\"size 39\", "
    "\"size 40\", \"size 41\", \"size 42\", \"size 43\"), and \"yellowyellowyellowyellowyellow"
    "blackblackblackblackblack\" means ten entries (\"yellow\" x5 then \"black\" x5). Carefully "
    "work out where each individual entry starts and ends (repeated words/prefixes, digit "
    "groups, and known color/size names are the cues) before doing anything else with them. If "
    "two of these variant columns have the same number of parsed entries, they describe the SAME "
    "set of variants and must be paired up positionally (1st entry of VARIAN 1 with 1st entry of "
    "VARIAN 2, 2nd with 2nd, etc.) — never treat them as independent lists to combine every-way. "
    "Each VARIAN_PRODUK line must be the FULL item name combined with that variant, not just the "
    "bare variant value by itself — e.g. write \"GOTO Camy Backpack Kids - Pink\" and \"GOTO Camy "
    "Backpack Kids - Blue\", never just \"Pink\" or \"Blue\" alone on a line. If, after pairing, "
    "one distinct value (e.g. one color) turns out to cover a contiguous numeric SIZE RANGE (e.g. "
    "sizes 39, 40, 41, 42, 43 all paired with \"yellow\"), collapse that into ONE line written as "
    "\"[Item Name] - Yellow - Ukuran 39 s.d. 43\" instead of five separate lines — but still write "
    "a separate line per genuinely distinct value (e.g. black gets its own \"...- Black - Ukuran "
    "39 s.d. 43\" line, since it's a different variant, not merged into the yellow line). "
    "FITUR_1 through FITUR_5 are individual bullet points, and ALL FIVE must be filled — never "
    "leave any of them as \"-\" or empty. First use every real, distinct feature genuinely "
    "supported by the data, in order. If the data supports fewer than 5 real features, fill "
    "the remaining slots yourself with plausible, generic features for this type of product "
    "based on its category/function (e.g. ease of use, durability, comfort, practical "
    "everyday benefits) — reasonable and true-to-category, but not a specific certification, "
    "capacity, or material that isn't in the data. Each of the 5 must be distinct, no repeats. "
    "DESKRIPSI_PRODUK is a warm, natural-sounding paragraph of 3-5 complete sentences — read it "
    "aloud in your head and it should sound like a person who actually knows this product "
    "wrote it, not a keyword-stuffed listing. Open by naming what the product concretely is, "
    "then weave in whatever real specifics ARE present in the data (material, size/dimensions, "
    "design details, category) into a sentence about what makes it distinctive, then close with "
    "a sentence about the everyday situation or use-case it's meant for. Never write a generic "
    "sentence that could apply to any product in that category — every sentence should feel "
    "grounded in this specific item's real data. FUNGSI_PRODUK is 1-2 sentences stating the "
    "concrete, practical benefit to the user (what problem it solves or what it lets them do "
    "day-to-day), not a restatement of DESKRIPSI_PRODUK. "
    "CARA_PENGGUNAAN and PERAWATAN are each EXACTLY 4 numbered steps (as a single string, steps "
    "separated by \\n, each starting with its number like \"1. \"), written generically based on "
    "the product type since exact steps aren't in the data. Each step must be a concrete, "
    "physical action a person actually performs (e.g. \"Rakit setiap bagian sesuai petunjuk "
    "pemasangan\", \"Letakkan pada permukaan yang rata dan stabil\", \"Bersihkan permukaan "
    "menggunakan kain lembut yang sedikit dibasahi\") — never a vague filler line like \"gunakan "
    "dengan hati-hati\" or \"ikuti petunjuk yang berlaku\". CARA_PENGGUNAAN covers first-use setup "
    "and normal operation; PERAWATAN covers cleaning, storage, and what to avoid so the product "
    "lasts. Base the specific actions on the product's actual category/material from the data "
    "(e.g. an assembled furniture item gets assembly + leveling steps, a fabric item gets "
    "hand-wash + air-dry steps, an electronic gets a power/battery step) rather than one "
    "generic script reused for every product type. "
    "NAMA_BARANG_DESKRIPSI is a short generic product-type label (e.g. \"Tas Ransel Anak\", "
    "\"Full Body Harness\") used in the template as \"Nama Barang: [product name] "
    "([NAMA_BARANG_DESKRIPSI])\" — do not repeat the product name itself here. ITEM_NAME and "
    "MADE_IN will be filled in separately, so you don't need to fill them."
)


DESCRIPTION_FIELDS = [
    "INTRO_PARAGRAPH", "SELLING_POINTS_BLOCK", "SPEC_LINES", "VARIAN_LIST_BLOCK", "FAQ_BLOCK",
]

DESCRIPTION_SYSTEM_INSTRUCTION = (
    "You are writing a marketplace product listing description (in Bahasa Indonesia) for an "
    "e-commerce store, in the style of a warm, benefit-driven Shopee/Tokopedia listing copy — "
    "not a dry technical manual. You are given raw vendor-sheet data for one product (and, if "
    "available, detailed variant specifications). Use ONLY information present in the data; "
    "never invent a certification, capacity, material, or specific claim that isn't there — but "
    "natural, generic marketing language (comfort, practicality, everyday convenience) is "
    "expected and fine, same as a real store listing would write.\n\n"
    "INTRO_PARAGRAPH is 2-4 warm, natural sentences: open with what the product concretely is, "
    "then its main benefit, then close by naming the specific everyday situations or use cases "
    "it's good for (e.g. \"Cocok untuk kopi, susu, matcha, cokelat, hingga minuman favorit "
    "lainnya.\") when the data supports naming a few.\n\n"
    "SELLING_POINTS_BLOCK is EXACTLY 5 numbered lines as a single string with \\n between them, "
    "each starting \"1. \" through \"5. \". Each point should read as a reason-to-buy benefit "
    "sentence (not a bare feature label) grounded in the product's real data — e.g. \"Desain "
    "compact dan hemat tempat, cocok untuk disimpan di berbagai area.\" If the data supports "
    "fewer than 5 concrete points, fill remaining slots with plausible, generic-but-true-to-"
    "category benefits (ease of use, durability, everyday practicality) rather than inventing "
    "specifics.\n\n"
    "SPEC_LINES is 2-5 lines as a single string with \\n between them, each \"Label: value\" "
    "(e.g. \"Material: PP + Stainless Steel\", \"Baterai: 300MA\") — use only the specs actually "
    "present in the data (material, dimensions, capacity, power/battery, certification, etc). "
    "Never pad with a made-up spec; if there's genuinely very little, just list what's there.\n\n"
    "VARIAN_LIST_BLOCK lists every distinct variant present in the data (color, size, model, "
    "etc.) as separate lines separated by \\n, each starting \"- \" — do not shorten, summarize, "
    "or drop any variant that's actually in the source data, no matter how many there are. The "
    "source data may have columns like \"VARIAN 1\", \"VARIAN 2\", \"VARIAN 3\" whose raw values "
    "are individual entries jammed together with NO space or separator at all — e.g. "
    "\"size 39size 40size 41size 42size 43\" means five separate entries (\"size 39\", "
    "\"size 40\", \"size 41\", \"size 42\", \"size 43\"), and \"yellowyellowyellowyellowyellow"
    "blackblackblackblackblack\" means ten entries (\"yellow\" x5 then \"black\" x5). Carefully "
    "work out where each individual entry starts and ends (repeated words/prefixes, digit "
    "groups, and known color/size names are the cues) before doing anything else with them. If "
    "two of these variant columns have the same number of parsed entries, they describe the SAME "
    "set of variants and must be paired up positionally (1st entry of VARIAN 1 with 1st entry of "
    "VARIAN 2, 2nd with 2nd, etc.) — never treat them as independent lists to combine every-way. "
    "Each line must be the FULL item name combined with that variant, not just the bare variant "
    "value by itself — e.g. write \"- GOTO Camy Backpack Kids - Pink\" and \"- GOTO Camy Backpack "
    "Kids - Blue\", never just \"- Pink\" or \"- Blue\" alone on a line. If, after pairing, one "
    "distinct value (e.g. one color) turns out to cover a contiguous numeric SIZE RANGE (e.g. "
    "sizes 39, 40, 41, 42, 43 all paired with \"yellow\"), collapse that into ONE line written as "
    "\"- [Item Name] - Yellow - Ukuran 39 s.d. 43\" instead of five separate lines. If the data "
    "genuinely has no distinct variants, write a single line \"- [Item Name]\" instead of "
    "inventing one.\n\n"
    "FAQ_BLOCK is EXACTLY 3 question-and-answer pairs as a single string, with a blank line "
    "(\\n\\n) between each pair, formatted exactly like:\\n\"1. [question]?\\n- [answer].\\n\\n"
    "2. [question]?\\n- [answer].\\n\\n3. [question]?\\n- [answer].\" Each question should be a "
    "genuine, common buyer "
    "question for this specific product type (usage, cleaning/care, versatility, durability — "
    "never shipping/order/payment questions, those are handled elsewhere), answered honestly "
    "and generically based on the product category since exact answers aren't in the data."
)


def build_description_prompt(row: dict[str, object], detail_text: str | None = None) -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    detail_block = f"\n\nDetailed variant specifications:\n{detail_text}" if detail_text else ""
    fields_list = "\n".join(f'  "{f}": ""' for f in DESCRIPTION_FIELDS)

    return (
        f"{DESCRIPTION_SYSTEM_INSTRUCTION}\n\n"
        f"--- Product data ---\n{row_block}{detail_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


# Maps each optional, toggleable instruction-manual section to the Gemini
# JSON field(s) that only make sense when that section is enabled — so a
# disabled section also stops wasting a generation on text nobody will see.
OPTIONAL_SECTION_FIELDS: dict[str, list[str]] = {
    "cara_penggunaan": ["CARA_PENGGUNAAN"],
    "perawatan": ["PERAWATAN"],
}


def build_instruction_manual_prompt(
    row: dict[str, object], detail_text: str | None, enabled_sections: dict[str, bool] | None = None,
) -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    detail_block = f"\n\nDetailed variant specifications:\n{detail_text}" if detail_text else ""

    disabled_fields = {
        field
        for key, fields in OPTIONAL_SECTION_FIELDS.items()
        if enabled_sections is not None and not enabled_sections.get(key, True)
        for field in fields
    }
    fields = [f for f in INSTRUCTION_MANUAL_FIELDS if f not in disabled_fields]
    fields_list = "\n".join(f'  "{f}": ""' for f in fields)

    return (
        f"{INSTRUCTION_MANUAL_SYSTEM_INSTRUCTION}\n\n"
        f"--- Product data ---\n{row_block}{detail_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


_USAGE_IMAGE_VARIATIONS = (
    "Frame it as a clear, front-on shot of the whole usage moment.",
    "Frame it as a three-quarter angle shot, and focus attention on the "
    "specific point of contact where hand/body meets the product (e.g. the "
    "grip, strap, buckle, or opening actually being used).",
    "Frame it as a candid, slightly wider shot showing the person and "
    "product in a complete real-world environment for this activity.",
)


def build_saran_penggunaan_image_prompt(row: dict[str, object], variation_index: int = 0) -> str:
    """Prompt for one "Saran Penggunaan" section image: an AI-generated photo
    (not text) showing the product's recommended real-world usage, grounded
    in the product's actual reference photo(s) so the generated image still
    shows the real product rather than a generic stand-in. When more than
    one such image is generated for the same product, pass a different
    variation_index for each call so they show distinct angles/moments of
    the same correct usage instead of near-identical repeats."""
    product = str(row.get("product_name") or "this product").strip()
    category = str(row.get("CATEGORY") or "").strip()
    category_hint = f" (category: {category})" if category else ""
    variation_hint = _USAGE_IMAGE_VARIATIONS[variation_index % len(_USAGE_IMAGE_VARIATIONS)]

    return (
        f"Using the exact product shown in the attached photo(s) of \"{product}\"{category_hint}, "
        "create a single photorealistic image that clearly illustrates the CORRECT, proper way "
        "to use it. First identify exactly what kind of product this is from the photo(s) and "
        "name, then show a person using/wearing/holding it in the one anatomically and "
        "functionally correct manner for that specific product type — get the orientation, body "
        "placement, and grip precisely right (e.g. a backpack worn on the back with both straps "
        "over both shoulders, never held against the chest or carried like a handbag; a cap or "
        "helmet worn on the head; gloves worn on the hands with fingers inserted; a bottle held "
        "upright by its body; a tool held by its handle in the hand meant to operate it). Do not "
        "guess a generic or approximate pose — if it's not the way this exact type of product is "
        "actually meant to be used, it's wrong. Look closely at every attached reference photo "
        "(there may be one or several) before drawing anything, and reproduce the product's exact "
        "colors exactly as shown across them — never invent, guess, shift, or blend a color that "
        "isn't actually visible in the reference photo(s). Preserve the product's exact shape, "
        "materials, logo, and details too — do not redesign, alter, or replace it with a "
        "different product. Square 1:1 framing, sharp and clearly lit, both the product and the "
        "usage action clearly visible and in focus, no text, no logos, no watermarks, no UI "
        "elements, no borders in the image itself. "
        f"{variation_hint}"
    )


BRAND_STYLE_HINTS: dict[str, str] = {
    "goto": (
        "This is for the GOTO brand — lean into a cute, playful, adorable, whimsical mood: "
        "soft rounded shapes, warm friendly colors, a fun and endearing feel."
    ),
    "gosave": (
        "This is for the GOSAVE brand — lean into a fierce, sharp, bold safety-gear mood: "
        "strong angular composition, high contrast, dramatic confident lighting, tough and "
        "protective energy."
    ),
    "safety_bro": (
        "This is for the SAFETY BRO brand — lean into a fierce, sharp, protective safety-gear "
        "mood: bold confident composition, strong contrast, dramatic lighting, tough and "
        "dependable energy."
    ),
    "ladder_bro": (
        "This is for the LADDER BRO brand — lean into a sharp, sturdy, dependable industrial "
        "mood: confident angular composition, strong contrast, dramatic lighting, rugged "
        "height-and-elevation energy."
    ),
}


def brand_style_hint(framing: str) -> str:
    return BRAND_STYLE_HINTS.get(framing, "")


GALLERY_KEYPOINTS_FIELDS = [
    "TAGLINE", "KEYPOINT_1", "KEYPOINT_2", "KEYPOINT_3", "BACKGROUND_SCENE", "FONT_THEME",
]

FONT_THEME_OPTIONS = ("modern_clean", "playful", "bold_industrial", "elegant")

GALLERY_KEYPOINTS_SYSTEM_INSTRUCTION = (
    "You are writing short marketing copy for a product graphic (in Bahasa Indonesia), "
    "based on the same vendor data used for this product's instruction manual. "
    "TAGLINE is a punchy 3-6 word tagline for the product. KEYPOINT_1 through KEYPOINT_3 are "
    "short 1-3 word selling points (e.g. \"Fall Protection\", \"Strong Hook\", \"Tahan Air\"). "
    "You should almost always be able to fill all 3 — look across the ENTIRE row, not just an "
    "obvious \"selling point\" field: material (e.g. waterproof fabric -> \"Tahan Air\"), "
    "category/function (e.g. safety gear -> \"Perlindungan Kerja\"), capacity, certification, "
    "dimensions/portability (e.g. compact size -> \"Ringan & Compact\"), variant count, or "
    "anything else genuinely present. Only 1-2 real keypoints "
    "(and empty strings for the rest) is a last resort for when the row is almost entirely "
    "blank — never invent a capability, material, or certification that has zero basis "
    "anywhere in the data, but do make a real effort to surface 3 distinct ones before "
    "giving up. Do not pad with generic filler like \"High Quality\" unless something in the "
    "data actually supports it. "
    "BACKGROUND_SCENE is a short English image-generation prompt (15-30 words) describing a "
    "specific, vivid, photorealistic real-world scene where THIS exact product would "
    "genuinely be used — grounded in its precise category/function/details in the data, not "
    "a generic catch-all. Go beyond just naming the room/location: pick a specific angle, "
    "time of day, and one or two concrete, believable environmental details (a particular "
    "surface material, a background element actually plausible for that setting) that make "
    "this scene feel like a real place, not a stock description. Two different products in "
    "the same broad category (e.g. two different kitchen tools, two different safety gloves) "
    "should still end up with two distinct-sounding scenes, not the same phrasing reused — "
    "vary the setting, angle, and mood based on THIS product's own specific details rather "
    "than defaulting to whatever scene the category most obviously suggests. Describe "
    "environment, lighting, and mood only — never mention the product itself, any brand "
    "name, or any text/logo, since the real product photo is composited on top separately. "
    "Default the lighting/mood to bright, clean daylight (soft sun or bright overcast) unless "
    "the product's own function specifically implies otherwise (e.g. a flashlight or a "
    "night-security light genuinely calls for a dark scene) — do NOT reach for dusk/night/"
    "rain/moody lighting just because it feels cinematic or matches the product's category "
    "loosely (a rain boot's scene should still default to a bright day, it doesn't need to "
    "literally be raining or dark). Only if the product's category/use case truly cannot be "
    "inferred at all from the data, describe a plain, neutral, brightly-lit studio backdrop "
    "as a last resort — never reach for that generic default just because it's easy; make a "
    "real attempt at a specific real-world setting first. Always keep the scene clean and "
    "uncluttered — a simple, believable environment with generous open/negative space, never "
    "a busy or visually noisy setting — since the product photo, headline, and badges all "
    "get composited on top of it afterward and need calm, uncrowded space to sit in. "
    "FONT_THEME picks the typography style for the card's title/tagline text based on the "
    "product's category — it must be EXACTLY one of these four values: "
    "\"modern_clean\" (bold sans-serif, the safe default for general/professional products — "
    "tools, electronics, household goods, safety gear), "
    "\"playful\" (rounded, friendly, handwritten-feel — for kids' toys, baby items, cute/fun "
    "products), "
    "\"bold_industrial\" (heavy, stark, condensed — for rugged/heavy-duty/construction/outdoor "
    "gear), "
    "\"elegant\" (refined serif — for premium home decor, beauty, or lifestyle products). "
    "Pick the single best match for this specific product's category — default to "
    "\"modern_clean\" only if none of the other three clearly fit better. "
    "Write in plain text, no markdown, no asterisks, no trailing punctuation."
)


def build_gallery_keypoints_prompt(row: dict[str, object], framing: str = "gosave") -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    fields_list = "\n".join(f'  "{f}": ""' for f in GALLERY_KEYPOINTS_FIELDS)
    hint = brand_style_hint(framing)
    brand_line = (
        f"\n\nWhen writing BACKGROUND_SCENE, let this brand's visual mood guide the scene "
        f"and lighting you describe: {hint}"
        if hint
        else ""
    )

    return (
        f"{GALLERY_KEYPOINTS_SYSTEM_INSTRUCTION}{brand_line}\n\n"
        f"--- Product data ---\n{row_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


GALLERY_SPEC_FIELDS = [
    "TAGLINE", "DESKRIPSI", "MEREK", "TIPE", "ITEM_NAME", "UKURAN", "MATERIAL",
    "RING_BUCKLE", "KAPASITAS", "APLIKASI", "ISI_KEMASAN",
]

GALLERY_SPEC_SYSTEM_INSTRUCTION = (
    "You are filling in the specification block for a product graphic (in Bahasa Indonesia), "
    "matching the layout of the brand's approved \"spesifikasi baru\" reference template — a "
    "title, a short description paragraph, then a bordered spec table, then bottom feature "
    "badges. Fill in the JSON fields below using ONLY information present in the data. Never "
    "invent a brand, type/model code, dimensions, material, capacity, or package contents "
    "that aren't in the data. If a field genuinely has no source data, write \"-\" instead of "
    "guessing — a field left as \"-\" is simply skipped when the card is drawn, so it's always "
    "safer to under-fill than to invent. "
    "TAGLINE is one short punchy line under the product title (e.g. \"Full Body Harness | "
    "Safety You Can Trust\"), generic and on-brand, never inventing a specific claim not "
    "in the data. "
    "DESKRIPSI is a short 2-3 sentence product description (e.g. \"Full body harness "
    "berkualitas tinggi yang dirancang untuk memberikan perlindungan maksimal, kenyamanan "
    "kerja lebih lama, dan ketahanan dalam berbagai kondisi kerja.\"), written in Bahasa "
    "Indonesia, summarizing only real selling points actually present in the data — never a "
    "specific certification or capability with no basis in the data. "
    "MEREK is the brand name. TIPE is the type/model code if present. ITEM_NAME is a short "
    "generic product-type label (e.g. \"Full Body Harness\", \"Fashion Safety Glasses\"), not "
    "a repeat of the product name. UKURAN is the product's dimensions (width/height/length, "
    "whatever is present) formatted like \"14 x 4.5 cm\" — only use dimension values actually "
    "present in the data. MATERIAL is a single short value (e.g. \"Polyester High Tenacity\"). "
    "RING_BUCKLE is the ring/buckle/hardware material if the product has this kind of "
    "component (e.g. \"Steel & High Strength Plastic\") — write \"-\" for products with no "
    "such part. KAPASITAS is a load/volume/weight capacity figure if the data states one "
    "(e.g. \"Maks. 100 Kg\", \"2 Liter\") — write \"-\" if no capacity figure exists in the "
    "data. APLIKASI is the product's intended use/application in a few words (e.g. "
    "\"Pekerjaan di Ketinggian\"), only if genuinely supported by the data. ISI_KEMASAN is "
    "the package contents (e.g. \"1 x Full Body Harness\"). Write in plain text, no markdown, "
    "no asterisks, no trailing punctuation."
)


def build_gallery_spec_prompt(row: dict[str, object], detail_text: str | None = None) -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    # The sheet row alone is often too thin for a full spec block (no
    # dimensions/material/etc) — the product's detail-link page usually has
    # the actual variant specs, same source already used for the instruction
    # manual, so pull from it here too instead of leaving fields as "-".
    detail_block = f"\n\nDetailed variant specifications:\n{detail_text}" if detail_text else ""
    fields_list = "\n".join(f'  "{f}": ""' for f in GALLERY_SPEC_FIELDS)

    return (
        f"{GALLERY_SPEC_SYSTEM_INSTRUCTION}\n\n"
        f"--- Product data ---\n{row_block}{detail_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


GALLERY_USAGE_FIELDS = [
    "SUBTITLE",
    "STEP_1", "STEP_2", "STEP_3", "STEP_4",
    "DESC_1", "DESC_2", "DESC_3", "DESC_4",
    "SCENE_1", "SCENE_2", "SCENE_3", "SCENE_4",
]

GALLERY_USAGE_SYSTEM_INSTRUCTION = (
    "You are writing a 4-step \"how to use\" sequence for a product graphic (in Bahasa "
    "Indonesia), based on the same vendor data used for this product's instruction manual. "
    "SUBTITLE is one short sentence (12-18 words) under the \"CARA PENGGUNAAN\" heading, "
    "e.g. \"Gunakan dengan benar untuk perlindungan maksimal dan kenyamanan saat bekerja.\" — "
    "generic, on-brand, about using this product correctly for safety/comfort/performance, "
    "never inventing a specific claim not in the data. "
    "STEP_1 through STEP_4 are short bold instruction titles (3-6 words each, imperative "
    "mood, e.g. \"Periksa bagian dalam sepatu boot\"), written generically based on the "
    "product's category/function since exact steps aren't in the data — never invent a "
    "capability or certification that has zero basis in the data, but ordinary generic usage "
    "steps for this type of product are expected and fine. "
    "DESC_1 through DESC_4 are one short supporting sentence each (6-12 words) that expands "
    "on its matching STEP with a bit more detail or the reason for that step, e.g. for STEP "
    "\"Periksa bagian dalam sepatu boot\" a fitting DESC could be \"Pastikan bersih dan tidak "
    "ada benda asing.\" — plain sentence, not a repeat of the STEP title. "
    "SCENE_1 through SCENE_4 are short English image-generation prompts (10-20 words) each "
    "describing a person actually performing that exact step with the product (e.g. wiping "
    "the product clean, putting it on, adjusting it, storing it away) — describe the action, "
    "framing, and setting only, never mention the product's brand name or any text/logo, "
    "since the real product photo is composited in separately. Each SCENE must clearly match "
    "its corresponding STEP. "
    "Write in plain text, no markdown, no asterisks, no trailing punctuation."
)


def build_gallery_usage_prompt(row: dict[str, object], framing: str = "gosave") -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    fields_list = "\n".join(f'  "{f}": ""' for f in GALLERY_USAGE_FIELDS)
    hint = brand_style_hint(framing)
    brand_line = (
        f"\n\nWhen writing SCENE_1 through SCENE_4, let this brand's visual mood guide the "
        f"framing and energy you describe: {hint}"
        if hint
        else ""
    )

    return (
        f"{GALLERY_USAGE_SYSTEM_INSTRUCTION}{brand_line}\n\n"
        f"--- Product data ---\n{row_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


GALLERY_KEUNGGULAN_FIELDS = [
    f"HEADLINE_{i}" for i in (1, 2, 3)
] + [
    f"EMPHASIS_{i}" for i in (1, 2, 3)
] + [
    f"POINT_{i}_{j}" for i in (1, 2, 3) for j in (1, 2, 3)
] + [
    f"SCENE_{i}" for i in (1, 2, 3)
]

GALLERY_KEUNGGULAN_SYSTEM_INSTRUCTION = (
    "You are writing copy for a set of up to 3 \"Fitur Keunggulan\" (product advantage "
    "highlight) posters, in Bahasa Indonesia, based on the same vendor data used for this "
    "product's instruction manual. Each of the 3 slots (suffix _1, _2, _3) is ONE self-"
    "contained poster built around ONE overall headline advantage, backed up by exactly 3 "
    "supporting points (like a mini keypoint list under that headline). Look across the "
    "ENTIRE row for real, distinct selling points (material, durability, comfort, safety "
    "feature, certification, capacity, design detail, ease of use, anything else genuinely "
    "present) — the headline of each slot should be its own clear theme (e.g. slot 1 about "
    "grip/traction, slot 2 about comfort, slot 3 about durability), and that slot's 3 points "
    "should all support and elaborate on that same theme from different angles, not repeat "
    "each other. Across the 3 slots, headlines must be clearly different themes, no repeats "
    "or near-duplicates. Only invent a plausible, generic, true-to-category advantage (never "
    "a specific certification, capacity, or material not in the data) for slots/points the "
    "data genuinely doesn't support after a real effort to ground them in real data.\n\n"
    "HEADLINE_n is a punchy, confident headline for that slot's theme, 4-8 words, written "
    "like real ad copy (e.g. \"Sol Luar yang Kokoh dan Tidak Licin\") — never a generic "
    "label. EMPHASIS_n is the exact short phrase (2-4 words) copied verbatim from within "
    "HEADLINE_n that should be visually highlighted in the brand accent color (usually the "
    "last, most punchy part of the headline, e.g. \"Tidak Licin\") — it must be an exact "
    "substring of HEADLINE_n, character for character. "
    "POINT_n_1, POINT_n_2, POINT_n_3 are the 3 supporting points for slot n's headline/theme "
    "— each a short, complete phrase or sentence, 4-8 words (e.g. \"Sol luar yang kokoh dan "
    "tidak licin\", \"Aman digunakan di berbagai medan\", \"Tahan air dan mudah "
    "dibersihkan\"), each a genuinely distinct fact/benefit that supports the headline's "
    "theme, never 3 rewordings of the same point. "
    "SCENE_n is a short English image-generation prompt (15-30 words) describing a dramatic "
    "close-up angle emphasizing specifically the part/aspect of the product that best "
    "represents slot n's overall theme, while the complete product still stays fully visible "
    "in frame, never cropped off (e.g. for a grip/traction theme: \"low dramatic angle on the "
    "boot's textured rubber sole gripping wet pavement, water droplets, whole boot visible\") "
    "— describe the framing, action, and lighting only, never mention the product's "
    "brand name or any text/logo, since the real product photo is composited in separately. "
    "Each SCENE_n must clearly match its own slot's theme, not a generic full-product shot "
    "repeated across all 3.\n\n"
    "Write in plain text, no markdown, no asterisks, no trailing punctuation."
)


def build_gallery_keunggulan_prompt(row: dict[str, object], framing: str = "gosave") -> str:
    visible = {k: v for k, v in row.items() if k not in ("source", "row_index", "detail_link", "marketing_picture_link")}
    row_block = _format_row_context(visible)
    fields_list = "\n".join(f'  "{f}": ""' for f in GALLERY_KEUNGGULAN_FIELDS)
    hint = brand_style_hint(framing)
    brand_line = (
        f"\n\nWhen writing SCENE_1 through SCENE_3, let this brand's visual mood guide the "
        f"framing and energy you describe: {hint}"
        if hint
        else ""
    )

    return (
        f"{GALLERY_KEUNGGULAN_SYSTEM_INSTRUCTION}{brand_line}\n\n"
        f"--- Product data ---\n{row_block}\n--- end of product data ---\n\n"
        f"Respond with ONLY a JSON object with exactly these keys:\n{{\n{fields_list}\n}}"
    )


PDF_TRANSLATE_SYSTEM_INSTRUCTION = (
    "You are a skilled human translator producing a Bahasa Indonesia version of the "
    "attached PDF document. Read the pages directly (including any pages that are scanned "
    "images with no text layer — read the text visible in the image itself). Write the "
    "way a native Indonesian professional would naturally phrase it — never a stiff, "
    "word-for-word machine translation. Restructure sentences when needed so they read "
    "smoothly and idiomatically in Indonesian, use natural everyday word choices instead "
    "of overly literal or overly formal dictionary equivalents, and make sure it flows the "
    "way something originally written in Indonesian would, not like something obviously "
    "translated. At the same time, never drift from the source's actual meaning, and "
    "translate the ENTIRE document completely, page by page — never summarize, shorten, "
    "or skip any part of it. If a heading, label, or table cell is in English (or another "
    "language), translate it too, still in natural phrasing. Keep numbers, product codes, "
    "units, and proper nouns (brand names) unchanged.\n\n"
    "Format the output using this simple markup, matching the document's own structure, "
    "so it can be turned into a properly formatted document afterwards:\n"
    "- Start every section title / heading line with '# ' (a single hash and a space).\n"
    "- Start every bullet or numbered list item with '- ' (a dash and a space) — turn "
    "numbered steps into '- ' items too, keeping the number as text if it matters "
    "(e.g. '- 1. Buka penutup baterai').\n"
    "- Leave a blank line between separate paragraphs.\n"
    "- Do not use any other markdown (no **, no backticks, no numbered '1.' list markers "
    "outside of '- ' items).\n"
    "Output ONLY the translated text in that markup — no commentary, no preamble like "
    "\"Here is the translation\", no notes about the document."
)


def build_pdf_translate_prompt() -> str:
    return PDF_TRANSLATE_SYSTEM_INSTRUCTION


IMAGE_TRANSLATE_SYSTEM_INSTRUCTION = (
    "You are a skilled human translator producing a Bahasa Indonesia version of the "
    "text visible in the attached image (e.g. a photographed or scanned document page). "
    "Read every piece of text visible in the image itself. Write the way a native "
    "Indonesian professional would naturally phrase it — never a stiff, word-for-word "
    "machine translation. Restructure sentences when needed so they read smoothly and "
    "idiomatically in Indonesian, use natural everyday word choices instead of overly "
    "literal or overly formal dictionary equivalents, and make sure it flows the way "
    "something originally written in Indonesian would, not like something obviously "
    "translated. At the same time, never drift from the source's actual meaning, and "
    "translate ALL of the text visible in the image completely — never summarize, "
    "shorten, or skip any part of it. If a heading, label, or table cell is in English "
    "(or another language), translate it too, still in natural phrasing. Keep numbers, "
    "product codes, units, and proper nouns (brand names) unchanged.\n\n"
    "Format the output using this simple markup, matching the image's own structure, so "
    "it can be turned into a properly formatted document afterwards:\n"
    "- Start every section title / heading line with '# ' (a single hash and a space).\n"
    "- Start every bullet or numbered list item with '- ' (a dash and a space) — turn "
    "numbered steps into '- ' items too, keeping the number as text if it matters "
    "(e.g. '- 1. Buka penutup baterai').\n"
    "- Leave a blank line between separate paragraphs.\n"
    "- Do not use any other markdown (no **, no backticks, no numbered '1.' list markers "
    "outside of '- ' items).\n"
    "Output ONLY the translated text in that markup — no commentary, no preamble like "
    "\"Here is the translation\", no notes about the image."
)


def build_image_translate_prompt() -> str:
    return IMAGE_TRANSLATE_SYSTEM_INSTRUCTION


def build_docx_translate_prompt(source_text: str) -> str:
    return (
        "You are a skilled human translator producing a Bahasa Indonesia version of the "
        "document text below. Write the way a native Indonesian professional would "
        "naturally phrase it — never a stiff, word-for-word machine translation. "
        "Restructure sentences when needed so they read smoothly and idiomatically in "
        "Indonesian, use natural everyday word choices instead of overly literal or "
        "overly formal dictionary equivalents, and make sure it flows the way something "
        "originally written in Indonesian would, not like something obviously translated. "
        "At the same time, never drift from the source's actual meaning, and translate "
        "the ENTIRE text completely — never summarize, shorten, or skip any part of it. "
        "If a heading or label is in English (or another language), translate it too, "
        "still in natural phrasing. Keep numbers, product codes, units, and proper nouns "
        "(brand names) unchanged.\n\n"
        "Format the output using this simple markup, matching the source's own structure, "
        "so it can be turned into a properly formatted document afterwards:\n"
        "- Start every section title / heading line with '# ' (a single hash and a space).\n"
        "- Start every bullet or numbered list item with '- ' (a dash and a space) — turn "
        "numbered steps into '- ' items too, keeping the number as text if it matters "
        "(e.g. '- 1. Buka penutup baterai').\n"
        "- Leave a blank line between separate paragraphs.\n"
        "- Do not use any other markdown (no **, no backticks, no numbered '1.' list "
        "markers outside of '- ' items).\n"
        "Output ONLY the translated text in that markup — no commentary, no preamble "
        "like \"Here is the translation\", no notes about the document.\n\n"
        "--- SOURCE DOCUMENT TEXT ---\n"
        f"{source_text}"
    )


DIAGRAM_REGION_PROMPT = (
    "Look at this scanned document page. Identify every distinct diagram, technical "
    "drawing, illustration, product photo, or numbered figure on the page — anything "
    "that is a picture, not text.\n\n"
    "The box for each diagram must be TIGHT and contain ONLY the drawing/illustration "
    "itself — never any surrounding sentence, caption, or instruction text, even if that "
    "text sits right next to, above, or below the drawing and looks visually related to "
    "it (e.g. a red or colored instruction sentence explaining the step). Only exception: "
    "a short marker/tag physically overlaid ON TOP of the drawing itself (like a small "
    "\"NO.1\" pill-shaped tag in a corner of the drawing, or a tiny circled part number "
    "pointing at a piece of the drawing) counts as part of the drawing and should stay "
    "inside its box. If you're unsure whether something is a caption sentence or an "
    "on-drawing tag, exclude it — a slightly tighter crop that clips a stray tag is "
    "better than one that drags in a caption.\n\n"
    "Do NOT include headings, paragraphs, bullet/numbered instruction text, or full "
    "caption sentences as their own regions, and do NOT let a box's edge stretch out to "
    "include them just because they're nearby. Each diagram should get its own tight "
    "bounding box — if the page has several separate diagrams (e.g. individual parts, "
    "then a separate assembled-product illustration, then several numbered step "
    "diagrams), return a separate box for each one rather than one box covering the "
    "whole page. If the page genuinely has no diagrams/illustrations at all (pure text), "
    "return an empty array.\n\n"
    "If a diagram has an on-drawing step marker/tag — e.g. \"NO.1\", \"NO.2\", \"Step 3\", "
    "or a small circled part number like \"6\" — report that exact marker text too, so "
    "the diagram can be matched back to the matching numbered step/part in the page's "
    "text. Use null if a diagram has no such marker (e.g. a general product photo).\n\n"
    "Respond with ONLY a JSON array, each item shaped like:\n"
    '{"box_2d": [ymin, xmin, ymax, xmax], "label": "short description", '
    '"reference_marker": "exact marker text, e.g. \\"NO.1\\", or null"}\n'
    "where box_2d coordinates are normalized to a 0-1000 scale relative to the full "
    "image (top-left is [0,0], bottom-right is [1000,1000])."
)


def build_diagram_region_prompt() -> str:
    return DIAGRAM_REGION_PROMPT


DIAGRAM_BOX_REFINE_PROMPT = (
    "This image is a candidate crop of a single diagram/technical drawing/illustration "
    "from a document page, with some extra margin left around it on purpose so nothing "
    "is missed. Your job is to find the TIGHT bounding box of just that one drawing "
    "within this image.\n\n"
    "Include the full drawing — every line, arrow, part, and shading that belongs to it "
    "— even if part of it sits close to or touches the edge of this image. Never let the "
    "box stop short and clip off part of the drawing. But exclude any surrounding "
    "caption/instruction sentences, headings, or empty page background that isn't part "
    "of the drawing itself. A small on-drawing marker/tag (e.g. a \"NO.1\" pill or a "
    "tiny circled part number) counts as part of the drawing.\n\n"
    "If the drawing already fills this entire image with no extra margin to trim, return "
    "a box covering the full image, i.e. [0, 0, 1000, 1000].\n\n"
    "Respond with ONLY a JSON object: {\"box_2d\": [ymin, xmin, ymax, xmax]}, coordinates "
    "normalized to a 0-1000 scale relative to this image (top-left is [0,0], bottom-right "
    "is [1000,1000])."
)


def build_diagram_box_refine_prompt() -> str:
    return DIAGRAM_BOX_REFINE_PROMPT
