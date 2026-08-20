from __future__ import annotations

import colorsys
import io
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage

import re

from adapters.llm import edit_image, generate_image, generate_image_from_references, generate_json
from config import settings
from core.prompts import (
    FONT_THEME_OPTIONS,
    brand_style_hint,
    build_fitur_produk_prompt,
    build_gallery_keunggulan_prompt,
    build_gallery_keypoints_prompt,
    build_gallery_spec_prompt,
    build_gallery_usage_prompt,
    FITUR_PRODUK_FIELDS,
)

try:
    from rembg import remove as _rembg_remove
except Exception:  # pragma: no cover - optional dependency
    _rembg_remove = None

logger = logging.getLogger(__name__)

CARD_SIZE = (1024, 1024)
# Colors matching the reference design spec's own color_palette exactly:
# primary #1E3A8A (navy), secondary #FFD500 (safety-yellow), accent #FFFFFF.
NAVY = (30, 58, 138)
NAVY_LIGHT = (46, 76, 158)
YELLOW = (255, 213, 0)
WHITE = (255, 255, 255)

# Manual color-palette presets a user can pick instead of the fixed brand
# navy/yellow — each is just a (primary, accent) pair, everything else
# (gradient light stop, ink colors, badge fills) is derived from these two
# so every palette still reads as "the same card, different colors" rather
# than a redesign.
COLOR_PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "navy_yellow": {"primary": NAVY, "accent": YELLOW},
    "red_white": {"primary": (185, 28, 28), "accent": (255, 255, 255)},
    "forest_cream": {"primary": (20, 83, 45), "accent": (245, 230, 200)},
    "purple_gold": {"primary": (76, 29, 149), "accent": (255, 200, 0)},
    "charcoal_orange": {"primary": (31, 41, 55), "accent": (255, 122, 26)},
}
DEFAULT_PALETTE = "navy_yellow"
PALETTE_OPTIONS = tuple(COLOR_PALETTES.keys())


DARK_INK = (18, 20, 26)


def _lighten(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Blend `color` toward white by `amount` (0 = unchanged, 1 = white)."""
    return tuple(round(c + (255 - c) * amount) for c in color)  # type: ignore[return-value]


def _darken(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    """Blend `color` toward black by `amount` (0 = unchanged, 1 = black)."""
    return tuple(round(c * (1 - amount)) for c in color)  # type: ignore[return-value]


def _luminance(color: tuple[int, int, int]) -> float:
    r, g, b = color
    return 0.299 * r + 0.587 * g + 0.114 * b


def _vivid_glow(color: tuple[int, int, int], value: float = 1.0, min_saturation: float = 0.55) -> tuple[int, int, int]:
    """Brighten `color` toward a vivid, saturated version of its own hue
    (boost V in HSV, floor S) instead of blending toward white like
    `_lighten` does. `_lighten` desaturates as it brightens, so a navy badge
    lightened enough to glow reads as a flat pale-white halo; the reference
    badges instead glow as an electric, saturated blue rim light that's
    still clearly "blue", not "white". Used for the badge's glow/rim-light,
    never for flat fills."""
    r, g, b = (c / 255 for c in color)
    h, s, _v = colorsys.rgb_to_hsv(r, g, b)
    s = max(s, min_saturation)
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, value)
    return (round(r2 * 255), round(g2 * 255), round(b2 * 255))


def hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    """Parse a "#rrggbb" / "rrggbb" string into an RGB tuple, or None if it
    isn't a valid 6-digit hex color — callers fall back to a palette preset
    on None rather than crashing on bad user input."""
    text = (value or "").strip().lstrip("#")
    if len(text) != 6:
        return None
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return None


def _theme_from_colors(
    primary: tuple[int, int, int], accent: tuple[int, int, int], dark_theme: bool,
) -> dict[str, tuple[int, int, int]]:
    """Resolve a raw (primary, accent) color pair + dark/light toggle into the
    actual colors a card should use. `primary`/`accent` (the badge/brand
    colors) stay fixed regardless of theme — only the gradient-fallback
    background and the main text "ink" color adapt, so switching Gelap/Terang
    always visibly changes the card instead of silently doing nothing when no
    AI background photo is available.

    Text ink is picked from the ACTUAL luminance of the resulting background,
    not just assumed from the dark/light toggle — a custom palette can pick a
    pale "primary" for dark mode, or a pale one for light mode too, and either
    would make white-on-light or dark-on-light text unreadable if it only
    looked at the toggle."""
    primary_light = _lighten(primary, 0.18)
    # A deeper, more saturated navy than the card's own background/gradient
    # for the keypoint badge circles specifically — when the badge used the
    # exact same "primary" as the dark-mode background's far gradient stop,
    # the two blended together and the circle read as flat/washed out
    # instead of a distinct, deep, professional badge color.
    badge = _darken(primary, 0.3)
    if dark_theme:
        gradient_near, gradient_far = primary_light, primary
    else:
        gradient_near, gradient_far = _lighten(primary, 0.90), _lighten(primary, 0.78)

    bg_luminance = _luminance(gradient_far)
    if bg_luminance < 150:
        ink = WHITE
    else:
        # Background reads light — prefer the palette's own (usually dark,
        # saturated) primary color for on-brand title text instead of flat
        # black, and only fall back to near-black if the primary itself
        # doesn't have enough contrast against this particular background
        # (e.g. a pale custom primary on top of its own pale gradient).
        ink = primary if abs(_luminance(primary) - bg_luminance) > 60 else DARK_INK
    # The accent color (tagline/eyebrow) keeps its own hue only if it's
    # actually readable against this background; a pale/bright custom accent
    # that's too close in luminance to the background falls back to the same
    # ink color as the title instead of disappearing into it.
    ink_accent = accent if abs(_luminance(accent) - bg_luminance) > 60 else ink

    return {
        "primary": primary,
        "primary_light": primary_light,
        "badge": badge,
        "accent": accent,
        "gradient_near": gradient_near,
        "gradient_far": gradient_far,
        "ink": ink,
        "ink_accent": ink_accent,
    }


def _theme_colors(
    palette: str, dark_theme: bool,
    custom_primary: str | None = None, custom_accent: str | None = None,
) -> dict[str, tuple[int, int, int]]:
    """Resolve a palette name (or a user-typed custom hex pair, when both are
    given and valid) + dark/light toggle into the actual card colors."""
    custom_rgb_primary = hex_to_rgb(custom_primary) if custom_primary else None
    custom_rgb_accent = hex_to_rgb(custom_accent) if custom_accent else None
    if custom_rgb_primary is not None and custom_rgb_accent is not None:
        return _theme_from_colors(custom_rgb_primary, custom_rgb_accent, dark_theme)

    resolved = COLOR_PALETTES.get(palette, COLOR_PALETTES[DEFAULT_PALETTE])
    return _theme_from_colors(resolved["primary"], resolved["accent"], dark_theme)

# Real icon glyphs cropped straight out of the two reference cards
# (contoh keypoint cell1.jpg / cell2.jpg) so badges use the actual brand
# artwork instead of a hand-drawn approximation. Falls back to a vector-drawn
# icon (below) for any keypoint that doesn't match one of these.
_ICONS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


def _load_icon_image(name: str) -> Image.Image:
    # Read fresh from disk every call, no in-memory cache — so swapping an
    # icon file on disk is picked up on the very next generate, with no
    # stale copy left sitting in memory from before the swap.
    return Image.open(_ICONS_DIR / f"{name}.png").convert("RGBA")


# Ready-made border + logo badge overlays (frontend/public/assets/Framing *.png),
# pasted on top of the finished card as-is instead of redrawing the frame/logo by
# hand — same real assets as the reference cards, exact pixels every time. One
# brand per option, picked per-generation instead of always defaulting to GOSAVE.
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FRAMING_FILES: dict[str, str] = {
    "gosave": "framing_gosave.png",
    "goto": "framing_goto.png",
    "ladder_bro": "framing_ladder_bro.png",
    "safety_bro": "framing_safety_bro.png",
}
DEFAULT_FRAMING = "gosave"
FRAMING_OPTIONS = tuple(FRAMING_FILES.keys())

# What kind of brand each framing actually is, and which real-world brands'
# ad campaigns its full-AI-design card prompts should be benchmarked
# against — the prompt used to hardcode "industrial safety equipment brand"
# and "3M/Honeywell/Caterpillar" for every product regardless of framing,
# which fought against BRAND_STYLE_HINTS's own "cute, playful, whimsical"
# mood for GOTO (a household/kids brand, not safety gear) and produced
# mismatched, overly-industrial backgrounds for it. Every framing now gets
# a category/benchmark that actually matches its own brand mood.
_BRAND_CATEGORY_LABEL: dict[str, str] = {
    "goto": "premium household, kids, and lifestyle goods",
    "gosave": "industrial safety equipment",
    "safety_bro": "industrial safety equipment",
    "ladder_bro": "industrial tools and equipment",
}
_STYLE_BENCHMARK: dict[str, str] = {
    "goto": "Xiaomi, MUJI, Tupperware, Fisher-Price, and IKEA",
    "gosave": "3M, Honeywell Safety, Caterpillar, Delta Plus, Ansell and Uvex",
    "safety_bro": "3M, Honeywell Safety, Caterpillar, Delta Plus, Ansell and Uvex",
    "ladder_bro": "3M, Honeywell, Caterpillar, DeWalt and Makita",
}
_DEFAULT_BRAND_CATEGORY = "premium consumer product"
_DEFAULT_STYLE_BENCHMARK = "3M, Honeywell Safety, Caterpillar, Delta Plus, Ansell and Uvex"


def _brand_category_label(framing: str) -> str:
    return _BRAND_CATEGORY_LABEL.get(framing, _DEFAULT_BRAND_CATEGORY)


def _style_benchmark(framing: str) -> str:
    return _STYLE_BENCHMARK.get(framing, _DEFAULT_STYLE_BENCHMARK)


def _load_framing_image(framing: str = DEFAULT_FRAMING) -> Image.Image:
    # Read fresh from disk every call, no in-memory cache — so swapping a
    # framing/badge asset on disk is picked up on the very next generate,
    # with no stale copy left sitting in memory from before the swap.
    filename = FRAMING_FILES.get(framing, FRAMING_FILES[DEFAULT_FRAMING])
    loaded = Image.open(_ASSETS_DIR / filename).convert("RGBA")
    if loaded.size != CARD_SIZE:
        loaded = loaded.resize(CARD_SIZE, Image.LANCZOS)
    return loaded


# Real finished example cards the brand actually approved (assets/) — handed
# to the full-AI-design prompts as a second reference image alongside the
# product cutout, so the model can literally see the target layout/style
# instead of only reading a text description of it. Best-effort: a missing
# file just means that card type's full-design path runs on the text prompt
# alone, same as before these existed.
# Per-brand (framing) style-reference overrides — checked first, before
# falling back to _STYLE_REFERENCE_FILES's own single default. A brand with
# a genuinely different visual mood (e.g. GOTO's playful streetwear look vs.
# GOSAVE's corporate-safety look) needs its own real example image, not the
# default brand's example reused as a stand-in — reusing it would bias every
# GOTO card toward GOSAVE's navy/corporate style regardless of the text
# brand-mood instructions elsewhere in the prompt.
_STYLE_REFERENCE_FILES_BY_FRAMING: dict[str, dict[str, str]] = {
    "keypoint": {"goto": "KEYPOINT CELL GOTO.jpg"},
}
_STYLE_REFERENCE_FILES: dict[str, str] = {
    "keypoint": "key point cell baru.png",
    "usage": "cara pengunaan baru.png",
    "spec": "spesifikasi baru.png",
    "keunggulan": "fitur unggulan.png",
    "varian": "varian baru.png",
}
def _style_reference_filename(card_type: str, framing: str) -> str | None:
    by_framing = _STYLE_REFERENCE_FILES_BY_FRAMING.get(card_type, {})
    return by_framing.get(framing) or _STYLE_REFERENCE_FILES.get(card_type)


def _load_style_reference_bytes(card_type: str, framing: str = DEFAULT_FRAMING) -> bytes | None:
    # Read fresh from disk every call, no in-memory cache — so swapping a
    # reference image on disk (e.g. assets/varian baru.png) feeds straight
    # into the very next generate, with no stale copy left in memory and
    # no server restart needed.
    filename = _style_reference_filename(card_type, framing)
    path = _ASSETS_DIR / filename if filename else None
    if path is None or not path.exists():
        return None
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _style_reference_instruction(card_type: str, framing: str = DEFAULT_FRAMING) -> str:
    """Prompt paragraph telling the model a second attached image is a real
    style reference, only added when that reference file actually exists —
    referencing a "second attached image" that was never actually attached
    would just confuse the model."""
    if _load_style_reference_bytes(card_type, framing) is None:
        return ""
    return (
        "\n\nREFERENCE IMAGE\n"
        "The second attached image is a real, brand-approved example of this exact card "
        "type — use it as your reference for the overall visual style, quality bar, and "
        "general feel (premium commercial product photography, typography weight, color "
        "mood). You have creative freedom on the actual composition/arrangement — it does "
        "not need to match the reference's exact element positions — but the one thing "
        "that must always hold, no exceptions: the main background stays clean and "
        "uncluttered, never busy, chaotic, or full of distracting visual noise. Use the "
        "product shown in the FIRST attached image, "
        "never the product shown in this reference image — the reference is for visual "
        "style only, not for its product. Also do NOT copy that reference image's own "
        "border, frame artwork, corner shapes, or logo badge — those belong to a "
        "different brand than the one being generated now, and a real, correct brand "
        "frame/logo for THIS brand is composited on top separately afterward. Leave the "
        "outer edges of your generated image plain/open exactly as instructed in the safe-"
        "zone section below, not styled to look like the reference's own border. IMPORTANT: "
        "this reference image was captured/exported WITHOUT any border frame ever being "
        "composited on top of it afterward, so its own headline text and product may sit "
        "much closer to its own edges — even flush against the top or bottom edge — than is "
        "safe for what you are generating now. Do NOT copy that tight, edge-hugging "
        "placement; it would get cropped or hidden once the real frame is pasted on top of "
        "your output. Follow the safe-interior margins given in the safe-zone section below "
        "exactly, even where they leave visibly more empty space around the text/product "
        "than this reference shows. Critically, "
        "the reference image belongs to a specific example brand — never render that "
        "brand's own name, wordmark, tagline, or logo text anywhere in your output, whether "
        "as the badge in the corner, printed on the product, or in any other text — the "
        "only brand name/wordmark that may ever appear is the one explicitly given for this "
        "generation below, nothing copied from the reference."
    )


def _generate_designed_card_image(
    prompt: str, cutout_photo: Image.Image, card_type: str, framing: str = DEFAULT_FRAMING,
) -> bytes:
    """Run a full-AI-design card prompt, grounded in the real product cutout
    plus — when one exists in assets/ — a real approved example card as a
    second reference image (see _STYLE_REFERENCE_FILES), so the model has
    an actual picture of the target style instead of only a text
    description of it, used for its visual style/quality bar rather than
    as a rigid template to copy pixel-for-pixel. A high generation
    temperature gives the model real creative freedom on the composition
    itself; the one hard requirement carried through every prompt is a
    clean, uncluttered main background, since that's what actually reads
    as broken/unprofessional, not a differently-arranged layout."""
    flattened = Image.new("RGB", cutout_photo.size, WHITE)
    flattened.paste(cutout_photo.convert("RGBA"), (0, 0), cutout_photo.convert("RGBA"))
    style_ref = _load_style_reference_bytes(card_type, framing)
    if style_ref is None:
        return edit_image(prompt, flattened)
    product_buffer = io.BytesIO()
    flattened.save(product_buffer, format="PNG")
    return generate_image_from_references(
        prompt, [product_buffer.getvalue(), style_ref], temperature=0.9,
    )


def _framing_safe_insets(framing: str) -> dict[str, int]:
    """How many pixels of margin the selected framing's own border/logo
    badge actually occupies on each edge of the card, measured straight off
    that framing's real pixels instead of a fixed guess — each brand's logo
    badge is a different size, so text needs a different safe zone per
    framing choice. Used to keep AI-added text (and the layout math around
    it) from landing under the frame, which is pasted on top afterward and
    would otherwise cover it. Recomputed from the framing image fresh on
    every call, no in-memory cache — so swapping a framing asset on disk
    takes effect on the very next generate."""
    alpha = np.array(_load_framing_image(framing).getchannel("A")) > 10
    h, w = alpha.shape
    row_cov = alpha.mean(axis=1)

    def _extent(coverage: np.ndarray, threshold: float = 0.06) -> int:
        limit = len(coverage) // 2
        last = 0
        for i in range(limit):
            if coverage[i] > threshold:
                last = i
        return last

    top = _extent(row_cov)
    bottom = _extent(row_cov[::-1])
    # Left/right border thickness only, scanned outside the top/bottom logo
    # badge rows — otherwise a wide top badge (which spans most of the
    # card's width) gets mistaken for a thick left/right border too.
    inner_rows = alpha[top + 10 : h - bottom - 10, :]
    col_cov = inner_rows.mean(axis=0) if inner_rows.shape[0] else alpha.mean(axis=0)
    left = _extent(col_cov)
    right = _extent(col_cov[::-1])
    # Right-half-only top extent — the logo badge sits in the top-left and
    # is what drives the full-width "top" measurement above, but the
    # right-aligned title/tagline text lives entirely on the right half of
    # the card and never gets near it. Using the full-width figure for that
    # text left a big, unnecessary dead zone above the title; this ignores
    # the left half so the text can start right under the card's own thin
    # top border instead of waiting out the logo's height too.
    top_right = _extent(alpha[:, w // 2 :].mean(axis=1))

    padding = 24
    return {
        "top": top + padding,
        "top_right": top_right + padding,
        "bottom": bottom + padding,
        "left": left + padding,
        "right": right + padding,
    }


_DEFAULT_FONT_THEME = "modern_clean"

# One (bold/medium/regular) candidate list per theme — AI picks the theme
# (see FONT_THEME_OPTIONS / GALLERY_KEYPOINTS_SYSTEM_INSTRUCTION) based on
# the product's category, so a kids' toy card and a construction-gear card
# don't share the same stiff sans-serif look. Each list still has fallbacks
# in case a given weight isn't installed on this machine.
_FONT_THEMES: dict[str, dict[str, list[str]]] = {
    "modern_clean": {
        # Century Gothic Bold — a geometric sans (round terminals, even
        # stroke weight) much closer to the clean, premium look of
        # marketplace badge cards (Poppins/Montserrat-style) than Arial
        # Black, which reads as blocky/generic at this weight. Arial Black
        # kept as a fallback for machines without Century Gothic installed.
        "bold": [
            "C:/Windows/Fonts/GOTHICB.TTF",
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/ariblk.ttf",
            "C:/Windows/Fonts/trebucbd.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        # A genuinely lighter weight than "bold" (Segoe UI Semibold, not
        # Century Gothic Bold again) — every piece of text on the card
        # sharing the exact same heavy weight is what actually reads as
        # stiff/monotone, not any single font choice. This is what gives
        # the tagline and keypoint labels their own lighter voice next to
        # the heavy title, instead of everything shouting at once.
        "medium": [
            "C:/Windows/Fonts/segoeuisb.ttf",
            "C:/Windows/Fonts/calibrib.ttf",
            "C:/Windows/Fonts/corbel.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ],
        "regular": [
            "C:/Windows/Fonts/GOTHIC.TTF",
            "C:/Windows/Fonts/trebuc.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ],
    },
    # Rounded, friendly — kids' toys, baby items, cute/fun products.
    "playful": {
        "bold": ["C:/Windows/Fonts/comicbd.ttf", "C:/Windows/Fonts/ariblk.ttf"],
        "medium": ["C:/Windows/Fonts/comicbd.ttf", "C:/Windows/Fonts/calibrib.ttf"],
        "regular": ["C:/Windows/Fonts/comic.ttf", "C:/Windows/Fonts/segoeui.ttf"],
    },
    # Heavy, stark, condensed — rugged/heavy-duty/construction/outdoor gear.
    "bold_industrial": {
        "bold": ["C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/ariblk.ttf"],
        "medium": ["C:/Windows/Fonts/tahomabd.ttf", "C:/Windows/Fonts/segoeuib.ttf"],
        "regular": ["C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/segoeui.ttf"],
    },
    # Refined serif — premium home decor, beauty, lifestyle products.
    "elegant": {
        "bold": ["C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/ariblk.ttf"],
        "medium": ["C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/calibrib.ttf"],
        "regular": ["C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/segoeui.ttf"],
    },
}


def _font(kind: str, size: int, theme: str = _DEFAULT_FONT_THEME) -> ImageFont.FreeTypeFont:
    candidates = _FONT_THEMES.get(theme, _FONT_THEMES[_DEFAULT_FONT_THEME])[kind]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    # Theme's own fonts weren't found on this machine — fall back to the
    # always-available default theme rather than PIL's tiny bitmap font.
    for path in _FONT_THEMES[_DEFAULT_FONT_THEME][kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def gallery_root() -> Path:
    root = Path(settings.workspace_dir) / "gallery_files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_product_dir(product_name: str) -> Path:
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in product_name).strip() or "product"
    product_dir = gallery_root() / safe
    product_dir.mkdir(parents=True, exist_ok=True)
    return product_dir


def photo_path(product_name: str) -> Path:
    return _safe_product_dir(product_name) / "source_photo.png"


def photo_meta_path(product_name: str) -> Path:
    return _safe_product_dir(product_name) / "source_photo.meta.json"


def read_photo_meta(product_name: str) -> dict[str, str] | None:
    """Where the current source photo came from ("uploaded" / "instruction_manual"
    / "sheet") and, for "sheet", which URL it was pulled from — so a later sheet
    sync can tell whether the link changed and a manual upload never gets
    silently clobbered by an auto-refresh."""
    path = photo_meta_path(product_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_photo_meta(product_name: str, source: str, source_url: str | None) -> None:
    meta = {"source": source}
    if source_url:
        meta["source_url"] = source_url
    photo_meta_path(product_name).write_text(json.dumps(meta), encoding="utf-8")


def cutout_path(product_name: str) -> Path:
    return _safe_product_dir(product_name) / "cutout_photo.png"


def _cards_dir(product_name: str) -> Path:
    cards_dir = _safe_product_dir(product_name) / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    return cards_dir


def photo_url_path(product_name: str) -> str:
    return f"/gallery-assets/{_safe_product_dir(product_name).name}/source_photo.png"


def chat_images_root() -> Path:
    root = Path(settings.workspace_dir) / "chat_images"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_chat_image(image_bytes: bytes) -> str:
    """Save one AI-chat-generated/edited image as a new timestamped file and
    return its public URL — same timestamped-file idea as gallery cards, so
    nothing ever gets overwritten and every turn of the conversation stays
    reproducible from disk."""
    filename = f"{int(time.time() * 1000)}.png"
    path = chat_images_root() / filename
    path.write_bytes(image_bytes)
    return f"/chat-assets/{filename}"


CARD_TYPES = ("keypoint", "spec", "usage")


def _parse_card_filename(stem: str) -> tuple[int, str]:
    """Card files are named "{timestamp_ms}__{card_type}" so multiple card
    types can share one history list and still be told apart / filtered.
    Old files saved before card types existed are just "{timestamp_ms}" and
    are treated as "keypoint" (the only type that existed back then)."""
    if "__" in stem:
        ts_part, card_type = stem.split("__", 1)
    else:
        ts_part, card_type = stem, "keypoint"
    return int(ts_part), card_type


def save_gallery_card(product_name: str, card_type: str, image_bytes: bytes) -> Path:
    """Save a generated card as a new timestamped file instead of overwriting
    the previous one, so every past "Generate ulang" result stays browsable
    as history instead of being lost the moment you regenerate."""
    filename = f"{int(time.time() * 1000)}__{card_type}.png"
    path = _cards_dir(product_name) / filename
    path.write_bytes(image_bytes)
    return path


def list_gallery_cards(product_name: str, card_type: str | None = None) -> list[dict[str, str]]:
    """All generated cards for this product, newest first. Pass card_type to
    only list one kind (keypoint/spec/usage)."""
    safe_name = _safe_product_dir(product_name).name
    files = sorted(_cards_dir(product_name).glob("*.png"), key=lambda p: p.name, reverse=True)
    history = []
    for f in files:
        timestamp_ms, file_card_type = _parse_card_filename(f.stem)
        if card_type is not None and file_card_type != card_type:
            continue
        generated_at = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()
        history.append({
            "url": f"/gallery-assets/{safe_name}/cards/{f.name}",
            "generated_at": generated_at,
            "card_type": file_card_type,
        })
    return history


def delete_gallery_card(product_name: str, filename: str) -> None:
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise FileNotFoundError(filename)
    path = _cards_dir(product_name) / filename
    if not path.exists():
        raise FileNotFoundError(filename)
    path.unlink()


def remove_card_frame(product_name: str, filename: str) -> Path:
    """AI-erase the brand border/logo badge from an already-generated card,
    reconstructing whatever the frame was covering, and save the result as a
    new history entry (same card_type, non-destructive — the original with
    its frame stays untouched). Unlike the deterministic frame *composite*
    step, there is no clean "pre-frame" pixels to fall back to here: this
    acts on a card that's already been saved to disk with the frame baked
    into the flat PNG, so the only way to get a frame-free version back out
    is to ask the image model to paint over/reconstruct that border area."""
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise FileNotFoundError(filename)
    path = _cards_dir(product_name) / filename
    if not path.exists():
        raise FileNotFoundError(filename)

    _, card_type = _parse_card_filename(Path(filename).stem)
    source = Image.open(path).convert("RGB")
    prompt = (
        "This image is a finished product marketing card that has a decorative brand "
        "border/frame around its outer edges and a logo badge in one corner. Remove ONLY "
        "that border frame and logo badge completely, and reconstruct whatever photo/"
        "background/text it was covering underneath so the result looks like a natural, "
        "complete image with no border or logo at all — plain clean edges, no gap, no "
        "smudge, no leftover outline where the frame used to be. Do not alter, redesign, "
        "recolor, move, or remove anything else on the card — the product photo, all "
        "headline/body text, and every other element must stay pixel-for-pixel the same "
        "as given, only the border frame and logo badge are erased."
    )
    result_bytes = edit_image(prompt, source)
    result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    if result.size != CARD_SIZE:
        result = result.resize(CARD_SIZE, Image.LANCZOS)
    return save_gallery_card(product_name, card_type, _to_png_bytes(result))


def refine_gallery_card(product_name: str, filename: str, instruction: str = "") -> Path:
    """General-purpose AI touch-up pass on an already-generated card — not
    limited to product position, can be any fix (color, wording, spacing,
    a design detail that looks off, etc.) the user asks for in plain text.
    Whatever the ask, the result must still read as a polished, professional
    e-commerce marketing card and must keep this card's own existing
    template/layout (frame, fonts, structure) intact rather than being
    redesigned from scratch — this is a touch-up on the current card, not a
    fresh generation. With no instruction, it's a general polish pass:
    fix only things that are clearly off (product cut off/miscentered,
    obvious layout glitch), leave anything already fine untouched.

    The product's real reference photo is passed in as a second grounding
    image alongside the card, and the prompt explicitly holds the card's
    product render to it — auto-generation sometimes drifts from the real
    product's actual look (wrong color/shape/detail), and a touch-up pass
    that only ever saw the already-drifted card has no way to know that and
    correct it back. Saved as a new history entry, same as
    remove_card_frame — the original stays untouched so a bad touch-up
    never destroys the last good version."""
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise FileNotFoundError(filename)
    path = _cards_dir(product_name) / filename
    if not path.exists():
        raise FileNotFoundError(filename)

    _, card_type = _parse_card_filename(Path(filename).stem)
    source = Image.open(path).convert("RGB")
    instruction = instruction.strip()
    if instruction:
        task = f'Apply this specific fix: "{instruction}".'
    else:
        task = (
            "General polish pass: fix only things clearly off — product cut off at an edge, "
            "badly off-center, an obvious layout/spacing glitch, text overlapping something. "
            "If it already looks fine, make no change at all rather than inventing a fix."
        )
    prompt = (
        "TASK: touch up one existing product marketing card image (first image) — this is a "
        "targeted edit on the current card, not a fresh redesign. A second image is also "
        "given: the product's real, unedited reference photo — use it as ground truth for "
        "what the product actually looks like. " + task + "\n\n"
        "RULES:\n"
        "- Keep this card's existing template intact: same overall layout/structure, same "
        "decorative frame border and logo badge position, same fonts and text hierarchy — "
        "unless the instruction above explicitly asks to change one of these.\n"
        "- PRODUCT ACCURACY: the product as rendered on the card must match the real "
        "reference photo (second image) — exact shape, color, material, label/logo detail, "
        "every part present. If the card's current product render has drifted from the real "
        "reference photo in any way (wrong color, missing/altered detail, distorted shape), "
        "correct it to match the reference photo as part of this touch-up, even if that "
        "wasn't explicitly asked for in the instruction.\n"
        "- Everything else not related to the requested fix or the product-accuracy rule "
        "above must stay exactly as it is in the input — don't regenerate the whole card "
        "from scratch.\n"
        "- The end result must read as a clean, professional e-commerce marketing card: "
        "well-balanced composition, legible text, no stray artifacts or glitches.\n"
        "Fill in any background revealed by a moved/resized element naturally, matching the "
        "surrounding scene/style."
    )

    try:
        cutout = get_cutout_photo(product_name)
        reference = Image.new("RGB", cutout.size, WHITE)
        reference.paste(cutout.convert("RGBA"), (0, 0), cutout.convert("RGBA"))
        card_buffer = io.BytesIO()
        source.save(card_buffer, format="PNG")
        ref_buffer = io.BytesIO()
        reference.save(ref_buffer, format="PNG")
        result_bytes = generate_image_from_references(
            prompt, [card_buffer.getvalue(), ref_buffer.getvalue()]
        )
    except Exception:
        # No product photo on file, or the reference grounding call failed —
        # fall back to the single-image edit (still applies the instruction,
        # just without the extra product-accuracy grounding).
        logger.exception("Reference-grounded refine failed for %s, falling back to single-image edit", product_name)
        result_bytes = edit_image(prompt, source)

    result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    if result.size != CARD_SIZE:
        result = result.resize(CARD_SIZE, Image.LANCZOS)
    return save_gallery_card(product_name, card_type, _to_png_bytes(result))


def _to_png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def latest_gallery_card_url(product_name: str, card_type: str) -> str | None:
    history = list_gallery_cards(product_name, card_type=card_type)
    return history[0]["url"] if history else None


def save_source_photo(
    product_name: str,
    image_bytes: bytes,
    *,
    source: str = "uploaded",
    source_url: str | None = None,
) -> Path:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    path = photo_path(product_name)
    image.save(path, format="PNG")
    _write_photo_meta(product_name, source, source_url)
    # A new photo invalidates any cutout cached from the old one.
    stale_cutout = cutout_path(product_name)
    if stale_cutout.exists():
        stale_cutout.unlink()
    return path


def _variants_dir(product_name: str) -> Path:
    variants_dir = _safe_product_dir(product_name) / "variants"
    variants_dir.mkdir(parents=True, exist_ok=True)
    return variants_dir


def _variant_photo_path(product_name: str, variant_id: str) -> Path:
    if Path(variant_id).name != variant_id:
        raise FileNotFoundError(variant_id)
    return _variants_dir(product_name) / f"{variant_id}.png"


def _variant_meta_path(product_name: str, variant_id: str) -> Path:
    if Path(variant_id).name != variant_id:
        raise FileNotFoundError(variant_id)
    return _variants_dir(product_name) / f"{variant_id}.meta.json"


def save_variant_photo(product_name: str, name: str, image_bytes: bytes) -> dict[str, str]:
    """Save one user-uploaded "Varian" reference photo, labeled with the
    variant name the user typed themselves (e.g. "Merah") — unlike every
    other card type, this content is never AI-guessed, since the whole
    point is showing the real, accurate look of each variant. Each upload
    is its own independent entry (not grouped under a shared variant
    record), so uploading several photos under the same name is exactly
    how a caller asks for several distinct "Varian" cards out of one
    generate click, same padding-free 1:1 idea as save_gallery_card's
    timestamped files."""
    variant_id = str(int(time.time() * 1000))
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    image.save(_variant_photo_path(product_name, variant_id), format="PNG")
    name = name.strip() or "Varian"
    _variant_meta_path(product_name, variant_id).write_text(
        json.dumps({"name": name}), encoding="utf-8",
    )
    safe_name = _safe_product_dir(product_name).name
    return {
        "id": variant_id,
        "name": name,
        "url": f"/gallery-assets/{safe_name}/variants/{variant_id}.png",
    }


def list_variant_photos(product_name: str) -> list[dict[str, str]]:
    """All saved "Varian" reference photos, newest first."""
    safe_name = _safe_product_dir(product_name).name
    files = sorted(_variants_dir(product_name).glob("*.png"), key=lambda p: p.name, reverse=True)
    items = []
    for f in files:
        variant_id = f.stem
        meta_path = _variant_meta_path(product_name, variant_id)
        name = "Varian"
        if meta_path.exists():
            try:
                name = json.loads(meta_path.read_text(encoding="utf-8")).get("name") or "Varian"
            except (OSError, ValueError):
                pass
        items.append({
            "id": variant_id,
            "name": name,
            "url": f"/gallery-assets/{safe_name}/variants/{f.name}",
        })
    return items


def delete_variant_photo(product_name: str, variant_id: str) -> None:
    photo_path_ = _variant_photo_path(product_name, variant_id)
    if not photo_path_.exists():
        raise FileNotFoundError(variant_id)
    photo_path_.unlink()
    meta_path = _variant_meta_path(product_name, variant_id)
    if meta_path.exists():
        meta_path.unlink()


def get_cutout_photo_for_variant(product_name: str, variant_id: str) -> Image.Image:
    """Background-removed version of one "Varian" reference photo — same
    freshly-recomputed-every-call idea as get_cutout_photo, and for the
    same reason: never let a one-off bad background-removal result stick
    around on disk waiting to be reused by a later generate."""
    path = _variant_photo_path(product_name, variant_id)
    source = Image.open(path).convert("RGBA")
    try:
        return remove_background(source)
    except Exception:
        logger.exception("Background removal failed for variant %s of %s, using original photo", variant_id, product_name)
        return source


def _keep_largest_blob(cutout: Image.Image) -> Image.Image:
    """If the source photo was actually a multi-shot marketplace collage
    (several product angles, a zoomed inset circle, tiny variant thumbnails)
    rather than one clean product photo, rembg happily keeps ALL of them as
    "foreground" — the composited card then shows a messy multi-part shape
    with pieces getting clipped by the photo box. Keep only the single
    largest connected blob (the main hero shot) and drop the rest."""
    alpha = np.array(cutout.getchannel("A"))
    mask = alpha > 20
    if not mask.any():
        return cutout

    labeled, count = ndimage.label(mask)
    if count <= 1:
        return cutout

    sizes = ndimage.sum(mask, labeled, index=range(1, count + 1))
    largest_label = int(np.argmax(sizes)) + 1
    keep_mask = labeled == largest_label

    new_alpha = np.where(keep_mask, alpha, 0).astype(np.uint8)
    result = cutout.copy()
    result.putalpha(Image.fromarray(new_alpha, mode="L"))
    return result


# Aspect ratios the image model's generation config actually accepts —
# picking the closest one to a source photo's real width/height keeps an
# edit (e.g. ai_isolate_product below) from being forced through a square
# canvas and coming back stretched/reframed away from the original photo's
# true proportions.
_SUPPORTED_ASPECT_RATIOS: dict[str, float] = {
    "1:1": 1.0, "4:5": 4 / 5, "5:4": 5 / 4, "3:4": 3 / 4, "4:3": 4 / 3,
    "2:3": 2 / 3, "3:2": 3 / 2, "9:16": 9 / 16, "16:9": 16 / 9, "21:9": 21 / 9,
}


def _nearest_aspect_ratio(image: Image.Image) -> str:
    ratio = image.width / image.height
    return min(_SUPPORTED_ASPECT_RATIOS, key=lambda key: abs(_SUPPORTED_ASPECT_RATIOS[key] - ratio))


def ai_isolate_product(image: Image.Image) -> Image.Image | None:
    """Best-effort AI cleanup pass for source photos that aren't a clean
    single-product shot — e.g. a full marketplace listing image with several
    product angles, badges, and text baked in, or a photo with a person's
    hands/body, a toy, or some other unrelated object sharing the frame with
    the product. rembg has no notion of "which region is the product" so it
    either keeps everything or clips randomly; an image-editing model can
    actually pick out the main hero shot and reconstruct whatever small part
    of it was hidden behind whatever gets removed. Returns None on any
    failure so the caller can fall back to the original photo."""
    prompt = (
        "This image may contain a single product photo, or a full marketplace "
        "listing collage with multiple product angles, close-up insets, badges, "
        "and text — it may also have a person, a model's hands/body, a toy, a "
        "pet, or some other unrelated object in the same shot as the product. "
        "Output ONLY the single main hero product shot — the clearest, most "
        "complete, front-facing view of the product, entirely by itself — "
        "centered on a plain flat white background. Remove every other element: "
        "extra angle shots, zoomed inset circles, badges, logos, text, "
        "watermarks, AND any person, hand, body part, toy, pet, or unrelated "
        "prop in the frame — the product must end up completely alone, with no "
        "person or object holding it, wearing it, or otherwise appearing next "
        "to it. If a hand, arm, or other object was only covering a small part "
        "of the product, reconstruct that hidden part naturally so the product "
        "looks fully whole and complete, matching its own real design — never "
        "leave a gap, cut, or missing chunk where something was removed. Do "
        "not redesign, recolor, or alter the product itself in any way — "
        "preserve its exact shape, materials, colors, and details."
    )
    source = image.convert("RGB")
    try:
        result_bytes = edit_image(prompt, source, aspect_ratio=_nearest_aspect_ratio(source))
        return Image.open(io.BytesIO(result_bytes)).convert("RGB")
    except Exception:
        logger.exception("AI product isolation failed, falling back to the original photo")
        return None


def remove_background(image: Image.Image) -> Image.Image:
    """Isolate the product from its original studio backdrop so it can float
    naturally over the AI-generated scene, instead of looking like a photo
    pasted on top of another photo. Runs an AI cleanup pass first (isolates
    the main product shot out of a busy listing photo, if that's what this
    is), then rembg for the actual pixel-accurate background removal."""
    if _rembg_remove is None:
        raise RuntimeError("rembg is not installed")

    isolated = ai_isolate_product(image)
    working_image = isolated if isolated is not None else image

    buffer = io.BytesIO()
    working_image.convert("RGB").save(buffer, format="PNG")
    result = _rembg_remove(buffer.getvalue())
    cutout = Image.open(io.BytesIO(result)).convert("RGBA")
    cutout = _keep_largest_blob(cutout)

    # Trim to the subject's actual bounds (plus a little breathing room) —
    # otherwise leftover empty margin from the source photo's framing gets
    # counted in the fit-to-box scaling later, making the product render
    # smaller on the card than it needs to.
    bbox = cutout.getchannel("A").getbbox()
    if bbox:
        pad = 12
        left, top, right, bottom = bbox
        left = max(0, left - pad)
        top = max(0, top - pad)
        right = min(cutout.width, right + pad)
        bottom = min(cutout.height, bottom + pad)
        cutout = cutout.crop((left, top, right, bottom))

    return cutout


def get_cutout_photo(product_name: str) -> Image.Image:
    """Background-removed product photo, freshly recomputed every call —
    deliberately NOT cached to disk. A cached cutout that came out wrong
    (e.g. the AI isolation pass mishandled a person/object in the source
    shot) would otherwise keep getting reused on every future "generate
    ulang" until someone thought to re-upload the photo; recomputing each
    time costs a couple extra seconds but means a bad cutout never sticks
    around longer than one generation."""
    stale = cutout_path(product_name)
    if stale.exists():
        stale.unlink()

    source = Image.open(photo_path(product_name)).convert("RGBA")
    try:
        return remove_background(source)
    except Exception:
        logger.exception("Background removal failed for %s, using original photo", product_name)
        return source


_GENERIC_KEYPOINT_FALLBACKS = ("Kualitas Terjamin", "Nyaman Digunakan", "Tahan Lama")


def generate_keypoints(row: dict[str, Any], framing: str = DEFAULT_FRAMING) -> dict[str, Any]:
    prompt = build_gallery_keypoints_prompt(row, framing)
    generated = generate_json(prompt)
    font_theme = str(generated.get("FONT_THEME") or "").strip()
    seen_keypoints: set[str] = set()
    keypoints = []
    for i in (1, 2, 3):
        value = str(generated.get(f"KEYPOINT_{i}") or "").strip()
        # The model occasionally repeats itself across slots (e.g. KEYPOINT_1
        # and KEYPOINT_2 both landing on "Kokoh") — that renders as two
        # visually identical badges, which reads as a broken card, not a
        # deliberate design. Keep only the first occurrence of each.
        if value and value.casefold() not in seen_keypoints:
            seen_keypoints.add(value.casefold())
            keypoints.append(value)
    # The 3 keypoint badges are fixed slots on the card — leaving one empty
    # when the AI only surfaced 1-2 real keypoints looks like a broken/unfinished
    # layout, not a deliberate "fewer keypoints" design. Pad with generic,
    # true-to-any-product filler (never a specific spec/claim) rather than ever
    # rendering fewer than 3 badges.
    for fallback in _GENERIC_KEYPOINT_FALLBACKS:
        if len(keypoints) >= 3:
            break
        if fallback not in keypoints:
            keypoints.append(fallback)
    return {
        "tagline": str(generated.get("TAGLINE") or "").strip(),
        "keypoints": keypoints,
        "background_scene": str(generated.get("BACKGROUND_SCENE") or "").strip(),
        "font_theme": font_theme if font_theme in FONT_THEME_OPTIONS else _DEFAULT_FONT_THEME,
    }


_GENERIC_KEUNGGULAN_FALLBACKS: list[dict[str, Any]] = [
    {
        "headline": "Kualitas Terjamin untuk Pemakaian Setiap Hari",
        "emphasis": "Kualitas Terjamin",
        "points": [
            "Dibuat dari material pilihan yang kokoh",
            "Diuji untuk pemakaian sehari-hari",
            "Tetap diandalkan meski dipakai intensif",
        ],
        "scene": "close-up product detail shot emphasizing build quality and material "
                 "texture, dramatic studio lighting",
    },
    {
        "headline": "Desain Nyaman untuk Pemakaian Sepanjang Hari",
        "emphasis": "Desain Nyaman",
        "points": [
            "Nyaman dipakai dalam waktu lama",
            "Desain ergonomis mengikuti bentuk tubuh",
            "Ringan sehingga tidak membebani aktivitas",
        ],
        "scene": "close-up shot of the product being worn/held comfortably, soft natural "
                 "lighting, shallow depth of field",
    },
    {
        "headline": "Performa Andal di Berbagai Kondisi Kerja",
        "emphasis": "Performa Andal",
        "points": [
            "Tetap bekerja optimal di berbagai medan",
            "Konsisten diandalkan di kondisi berat",
            "Memberi ketenangan lebih saat digunakan",
        ],
        "scene": "dramatic close-up of the product in an active industrial/commercial use "
                 "scenario, cinematic lighting",
    },
    {
        "headline": "Praktis Digunakan Kapan Saja",
        "emphasis": "Praktis Digunakan",
        "points": [
            "Mudah dipakai tanpa perlu ribet",
            "Cocok dibawa untuk berbagai aktivitas",
            "Menghemat waktu dan tenaga penggunanya",
        ],
        "scene": "close-up shot of hands easily operating/using the product, bright clean "
                 "lighting, everyday practical context",
    },
    {
        "headline": "Tampilan Menarik dan Fungsional",
        "emphasis": "Menarik dan Fungsional",
        "points": [
            "Desain yang enak dipandang",
            "Tetap mengutamakan fungsi dan kegunaan",
            "Cocok dipakai di berbagai suasana",
        ],
        "scene": "close-up shot highlighting the product's overall design details, soft "
                 "studio lighting, clean background",
    },
]


def generate_keunggulan_content(
    row: dict[str, Any], framing: str = DEFAULT_FRAMING, count: int = 3,
) -> list[dict[str, Any]]:
    """count (1-5) distinct "Fitur Keunggulan" posters, each grounded in one
    "Fitur Produk" bullet — the same feature list used in this product's
    instruction manual — so the gallery posters and the instruction manual
    stay consistent instead of being independently re-derived from the raw
    sheet row. Each poster is its own self-contained headline theme (plus
    the exact phrase within it to accent-color) backed by exactly 3 short
    supporting points and a close-up scene hint, one AI call covering all
    slots at once. Padded with generic, true-to-any-product fallbacks (never
    a specific unearned claim) so a caller asking for N images always gets N
    genuinely distinct-looking posters, same padding policy as
    generate_keypoints."""
    count = max(1, min(5, count))

    fitur_prompt = build_fitur_produk_prompt(row)
    fitur_generated = generate_json(fitur_prompt)
    fitur_list = [
        str(fitur_generated.get(field) or "").strip() for field in FITUR_PRODUK_FIELDS
    ]
    fitur_list = [f for f in fitur_list if f]
    # The instruction-manual-style prompt is written to always fill all 5,
    # but fall back to the generic fallbacks' headlines as feature stand-ins
    # if the AI call came back short, so there's always enough to ground
    # `count` slots on.
    for fallback in _GENERIC_KEUNGGULAN_FALLBACKS:
        if len(fitur_list) >= count:
            break
        if fallback["headline"] not in fitur_list:
            fitur_list.append(fallback["headline"])
    fitur_list = fitur_list[:count]

    prompt = build_gallery_keunggulan_prompt(row, fitur_list, framing)
    generated = generate_json(prompt)
    items: list[dict[str, Any]] = []
    seen_headlines: set[str] = set()
    for i in range(1, count + 1):
        headline = str(generated.get(f"HEADLINE_{i}") or "").strip()
        seen_points: set[str] = set()
        points = []
        for j in (1, 2, 3):
            point = str(generated.get(f"POINT_{i}_{j}") or "").strip()
            # Same repeat-across-slots risk as the keypoint badges — a
            # duplicated point reads as a broken/copy-pasted card, so only
            # the first occurrence of each distinct point is kept.
            if point and point.casefold() not in seen_points:
                seen_points.add(point.casefold())
                points.append(point)
        # A headline repeated from an earlier slot in this same batch would
        # produce two visually near-identical posters — skip it (this slot
        # then falls through to a generic fallback below) rather than
        # rendering the same "distinct advantage" twice.
        if not headline or len(points) < 3 or headline.casefold() in seen_headlines:
            continue
        seen_headlines.add(headline.casefold())
        items.append({
            "headline": headline,
            "emphasis": str(generated.get(f"EMPHASIS_{i}") or "").strip(),
            "points": points,
            "scene": str(generated.get(f"SCENE_{i}") or "").strip(),
        })
    for fallback in _GENERIC_KEUNGGULAN_FALLBACKS:
        if len(items) >= count:
            break
        if fallback["headline"].casefold() not in seen_headlines:
            seen_headlines.add(fallback["headline"].casefold())
            items.append(fallback)
    return items[:count]


def generate_spec_data(row: dict[str, Any], detail_text: str | None = None) -> dict[str, str]:
    prompt = build_gallery_spec_prompt(row, detail_text)
    generated = generate_json(prompt)
    data = {
        field.lower(): str(generated.get(field) or "-").strip() or "-"
        for field in (
            "MEREK", "TIPE", "ITEM_NAME", "UKURAN", "MATERIAL",
            "RING_BUCKLE", "KAPASITAS", "APLIKASI", "ISI_KEMASAN",
        )
    }
    data["tagline"] = str(generated.get("TAGLINE") or "").strip()
    data["deskripsi"] = str(generated.get("DESKRIPSI") or "").strip()
    return data


def generate_usage_data(row: dict[str, Any], framing: str = DEFAULT_FRAMING) -> dict[str, Any]:
    """A subtitle sentence plus up to 4 "how to use" steps, each with a bold
    title, a short supporting description, and an image-gen scene
    description for that exact step. Steps with no real title are dropped
    rather than padded, same policy as the keypoints."""
    prompt = build_gallery_usage_prompt(row, framing)
    generated = generate_json(prompt)
    steps = []
    seen_captions: set[str] = set()
    for i in range(1, 5):
        caption = str(generated.get(f"STEP_{i}") or "").strip()
        # Same repeat-across-slots risk as the keypoint badges — a step
        # duplicated from an earlier slot reads as a broken card (two
        # identical numbered steps), so only the first occurrence is kept.
        if not caption or caption.casefold() in seen_captions:
            continue
        seen_captions.add(caption.casefold())
        steps.append({
            "caption": caption,
            "desc": str(generated.get(f"DESC_{i}") or "").strip(),
            "scene": str(generated.get(f"SCENE_{i}") or "").strip(),
        })
    return {
        "subtitle": str(generated.get("SUBTITLE") or "").strip(),
        "steps": steps,
    }


def generate_usage_step_photo(
    cutout_photo: Image.Image, product_name: str, scene_description: str, framing: str = DEFAULT_FRAMING,
) -> Image.Image | None:
    """AI-generated photo of a person performing one "how to use" step with
    this exact product, for one circular thumbnail on the usage card.
    Best-effort: on any failure, the caller falls back to just showing the
    plain product cutout in that slot instead of failing the whole step."""
    if not scene_description:
        return None

    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    prompt = (
        f"Using the exact product shown in the attached image, create a photorealistic photo "
        f"illustrating this step of using \"{product_name}\": {scene_description}. Preserve "
        "the product's exact shape, colors, materials, logo, and details — do not redesign or "
        "alter it. Natural lighting, real contrast between lit and shadowed areas — do not "
        "apply a flat dark tint or vignette over the image. Square 1:1 framing, the product "
        "and action clearly visible and centered, no text, no logos, no watermarks, no UI "
        f"elements, no borders in the image itself.{brand_line}"
    )
    flattened = Image.new("RGB", cutout_photo.size, WHITE)
    flattened.paste(cutout_photo.convert("RGBA"), (0, 0), cutout_photo.convert("RGBA"))

    try:
        result_bytes = edit_image(prompt, flattened)
        return Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    except Exception:
        logger.exception(
            "Usage step photo generation failed for %s, falling back to plain cutout", product_name,
        )
        return None


def _drop_tiny_specks(binary: np.ndarray, min_area_ratio: float = 0.03, min_area_px: int = 25) -> np.ndarray:
    """Remove only genuinely tiny disconnected flecks (stray artifacts the
    image model sometimes leaves in what's meant to be flat background),
    not every piece of the shape that isn't the single largest blob — an
    icon can legitimately be made of several separate pieces (a crown's
    points, a medal's ribbon tails, dots, a checkmark with a gap), and
    keeping only the biggest one used to chop those off and leave a
    mangled, partial icon."""
    labeled, num_features = ndimage.label(binary)
    if num_features <= 1:
        return binary
    sizes = ndimage.sum(binary, labeled, index=range(1, num_features + 1))
    keep_threshold = max(min_area_px, sizes.max() * min_area_ratio)
    keep_labels = {i + 1 for i, s in enumerate(sizes) if s >= keep_threshold}
    return np.isin(labeled, list(keep_labels))


def _feather_binary_mask(binary: np.ndarray, feather_px: float = 1.6) -> np.ndarray:
    """Turn a crisp binary mask into a tiny anti-aliased edge band (a couple
    pixels either side of the true boundary) via a distance transform —
    gives a clean, non-jagged silhouette without the broad blur/ghosting a
    general-purpose photo matting model's own raw alpha output has, which
    reads as smudged rather than a crisp flat icon."""
    dist_in = ndimage.distance_transform_edt(binary)
    dist_out = ndimage.distance_transform_edt(~binary)
    signed = np.where(binary, dist_in, -dist_out)
    alpha = np.clip((signed + feather_px) / (2 * feather_px), 0.0, 1.0)
    return (alpha * 255).astype(np.uint8)


def _white_rgba_from_alpha(alpha_u8: np.ndarray) -> Image.Image:
    out_arr = np.zeros((*alpha_u8.shape, 4), dtype=np.uint8)
    out_arr[..., 0:3] = 255
    out_arr[..., 3] = alpha_u8
    out = Image.fromarray(out_arr, "RGBA")
    bbox = out.getbbox()
    return out.crop(bbox) if bbox else out


def _extract_white_silhouette(image: Image.Image, bg_color: tuple[int, int, int]) -> Image.Image:
    """Turn a flat icon-on-solid-background image into a white silhouette
    with transparency, the same way the reference icons (assets/icons/)
    were extracted from the brand template, so the generated icon matches
    the badge's white-glyph style exactly.

    Prefers rembg's actual subject-segmentation model over a plain color-
    distance cutoff — the requested background color is only ever a
    prompt instruction, and an image model frequently renders it a little
    off (a slightly different navy, a subtle gradient/vignette it added on
    its own), which a hard color-distance threshold has no way to tell
    apart from the icon itself and either eats into the icon or leaves
    background residue. Only rembg's binary subject mask is trusted,
    though — its own raw alpha is soft, photo-matting-style blur (built
    for hair/fur edges), which read as a smudged icon instead of a crisp
    one; the actual edge anti-aliasing is redone from scratch off that
    binary mask. Falls back to color-distance only if rembg isn't
    installed."""
    if _rembg_remove is not None:
        try:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="PNG")
            cutout = Image.open(io.BytesIO(_rembg_remove(buffer.getvalue()))).convert("RGBA")
            alpha = np.asarray(cutout.getchannel("A"))
            binary = _drop_tiny_specks(alpha > 128)
            if binary.any():
                return _white_rgba_from_alpha(_feather_binary_mask(binary))
        except Exception:
            logger.exception("rembg icon extraction failed, falling back to color-distance cutout")

    distance_thresh = 90
    rgb = image.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32)
    dist = np.sqrt(((arr - np.array(bg_color, dtype=np.float32)) ** 2).sum(axis=2))
    binary = _drop_tiny_specks(dist > distance_thresh)
    return _white_rgba_from_alpha(_feather_binary_mask(binary))


ICON_SHAPE_HINTS: dict[str, str] = {
    "goto": "Soft, rounded, playful shape language, cute and friendly.",
    "gosave": "Sharp, angular, bold shape language, tough and confident.",
    "safety_bro": "Sharp, angular, bold shape language, tough and confident.",
    "ladder_bro": "Sharp, angular, sturdy shape language, rugged and confident.",
}


def generate_keypoint_icon(
    keypoint: str, primary_color: tuple[int, int, int] = NAVY, framing: str = DEFAULT_FRAMING,
) -> Image.Image | None:
    """AI-generated icon glyph for a single keypoint badge, so the icon itself
    reflects what the keypoint actually says (not just a keyword match against
    a fixed set). Best-effort: on any failure, callers fall back to a
    keyword-matched icon instead of failing the whole card."""
    if not keypoint:
        return None

    navy_hex = "#%02x%02x%02x" % primary_color
    shape_hint = ICON_SHAPE_HINTS.get(framing, "")
    shape_line = f" {shape_hint}" if shape_hint else ""
    prompt = (
        f"A single thin OUTLINE/stroke vector icon glyph for the concept \"{keypoint}\", in "
        f"the exact style of Feather Icons or Material Symbols \"outlined\" style — a "
        f"slender, uniform 2-2.5px stroke on a transparent-feeling interior (not filled "
        f"solid), simple, and instantly recognizable even at very small size. If the "
        f"concept expresses two ideas at once (e.g. \"Ringan & Stylish\"), pick only the "
        f"single most visually iconic one of the two and draw that alone — never combine "
        f"two different objects into one glyph (e.g. never a feather merged with a shoe). "
        f"Use the single most common, universally understood symbol for whichever one "
        f"concept you picked (for example: a water droplet for water-resistance, a shield "
        f"for safety/protection, a lightning bolt for power/speed, a padlock for security/"
        f"locking, a price tag for affordability, a chain link for strength/durability, an "
        f"eye for visibility, a feather for light weight, a medal/ribbon badge for high "
        f"quality, a checkmark for reliability/guarantee, a single tap finger for ease of "
        f"use/installation, a shoe sole with grip tread grooves for anti-slip/traction, a "
        f"clock or stopwatch for fast/time-saving, a recycle arrow loop for eco-friendly/"
        f"reusable, a flexed arm or dumbbell for heavy-duty/strength, a folded cloth or "
        f"sparkle-free surface for easy-to-clean) rather than a literal illustration of an "
        f"unrelated object, animal, or scene. Reduce the concept to 1-3 simple outlined "
        f"shapes with clean smooth stroke lines — no fine internal linework, no texture, no "
        f"hatching, no fur/feather/wood-grain detail, no small decorative elements, nothing "
        f"that would turn into visual noise once shrunk down. Flat, front-facing 2D outline "
        f"only — absolutely no 3D, no isometric or perspective view, no bevels, no depth, "
        f"no solid fill inside the shape. White stroke line on a plain solid background "
        f"colored exactly {navy_hex}. No text, no words, no letters, no logo, no gradient, "
        f"no shadow, no photo, no realistic rendering — outline icon glyph only.{shape_line}"
    )
    try:
        image_bytes = generate_image(prompt)
        generated = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        icon = _extract_white_silhouette(generated, primary_color)
        if icon.width < 4 or icon.height < 4:
            return None
        return icon
    except Exception:
        logger.exception("Icon generation failed for keypoint %r, falling back", keypoint)
        return None


def generate_background_image(
    scene_description: str, framing: str = DEFAULT_FRAMING,
) -> Image.Image | None:
    """AI-generated background photo matching the product's real-world context.
    Best-effort: on any failure, callers fall back to the plain brand gradient
    instead of failing the whole card — a missing background is much less bad
    than a broken generate button."""
    if not scene_description:
        return None

    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    prompt = (
        f"A photorealistic background scene: {scene_description}. "
        "Square framing, shallow depth of field, no people in the extreme foreground, no "
        "text, no logos, no watermarks, no product packaging visible — this is purely an "
        "environmental backdrop a product photo will be composited onto afterwards. You "
        "decide the lighting and mood freely — whatever genuinely fits this scene and "
        "product best, dark or bright or anything between, no fixed rule. Just make it "
        "real: natural directional light with true contrast and depth, never a flat tint, "
        "vignette, or filter laid over the whole frame. Use the scene's own true, natural "
        f"colors — do NOT apply any blue, navy, or other color tint/grade over the "
        f"image. Sharp and detailed throughout.{brand_line}"
    )
    try:
        image_bytes = generate_image(prompt)
        return Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception:
        logger.exception("Background image generation failed, falling back to gradient")
        return None


def generate_product_scene(
    cutout_photo: Image.Image, product_name: str, scene_description: str, with_model: bool,
    framing: str = DEFAULT_FRAMING, layout: str = "keypoint",
) -> Image.Image | None:
    """Let the AI decide the product's positioning, framing, and environment
    as one photorealistic shot, instead of floating a fixed-size cutout over
    a separately-generated background — optionally showing a person actually
    using/wearing the product. Takes the already-isolated product photo as
    input so the product's real appearance is preserved; best-effort, since
    a bad generation here just falls back to the plain cutout+background
    compositing path instead of failing the whole card.

    `layout` picks which parts of the frame need to stay calm/uncluttered
    for content overlaid afterwards: "keypoint" (used by the keypoint and
    spec cards) reserves the upper-right and top-left corner for a headline
    and badges; "usage" (the "cara penggunaan" card) instead reserves a
    full-width band at the very top for the heading and another at the very
    bottom for the row of numbered step photos, so the product itself never
    ends up sitting where those get overlaid."""
    model_instruction = (
        "Include one person naturally using, wearing, or holding this exact product in "
        "the scene, so its real-world use is obvious at a glance — show the product "
        "clearly, not obscured by the person."
        if with_model
        else "Do not include any person in the scene — the product should be shown by "
        "itself, naturally placed in the environment (resting on a surface, hanging, "
        "standing, etc. as fits the product)."
    )
    mood_instruction = (
        "award-winning, luxury commercial product photography — the quality bar of a "
        f"flagship {_style_benchmark(framing)} advertising campaign, "
        "not a plain snapshot. DEFAULT to bright, clean daylight — soft golden-hour sun or "
        "bright even daytime/overcast light, the whole scene clearly and comfortably lit, "
        "airy and inviting. Only use a darker/moody/night/dramatic-shadow look if the "
        "environment description below explicitly calls for one (mentions night, dusk, "
        "indoor/dim, dramatic, moody, or similar) — in every other case, bright wins. Soft "
        "realistic shadows, and naturalistic reflections on any wet/polished/glossy surface "
        "in frame. Whatever the mood, it must always look intentional, clearly visible, and "
        "premium, never accidentally underexposed, murky, or muddy from a lack of light. "
        "Shallow depth of "
        "field: the product in extremely sharp, hyper-detailed focus (every texture, seam, "
        "and surface detail crisp) while the environment behind it falls into a soft, gentle "
        "blur. Clean, uncluttered composition — no random background text, signage, logos, "
        "or brand names anywhere in the scene (real or fictional), no visual noise competing "
        "with the product. Use the scene's own true, natural colors — do NOT apply any blue, "
        "navy, or other color tint/grade over the image. Do NOT apply a flat tint, vignette, "
        "or filter over the whole frame; "
        "any light or shadow must come from a real source in the scene, never an overlay."
    )
    scene_hint = f" Environment: {scene_description}." if scene_description else ""
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    composition_instruction = (
        "Compose the shot with the product/person centered horizontally, within the middle "
        "vertical band of the frame, with generous margin from the left and right edges. Keep "
        "a calm, uncluttered strip spanning the full width of the frame at the very top "
        "(roughly its top fifth) and another spanning the full width at the very bottom "
        "(roughly its bottom third) — soft focus, open space, plain surface or wall, but "
        "still part of the same continuous photo — so a text headline can be overlaid at the "
        "top and a row of small numbered step photos can be overlaid at the bottom "
        "afterwards, without either one ever covering, cropping through, or competing with "
        "the product itself, which must stay fully inside that calm middle band. For usage "
        "layout, the lowest visible edge of the product/person must stay above 64% of the "
        "image height; the bottom third is reserved overlay space, not product space."
        if layout == "usage"
        else "Compose the shot with the product/person positioned toward the "
        "left half of the frame with generous margin from all four edges, and keep the "
        "upper-right area and right-hand third of the scene visually calm and uncluttered "
        "(soft focus, plain wall, open space, etc., but still part of the same continuous "
        "photo) so a text headline and small icon badges can be overlaid there afterwards — "
        "also keep the extreme top-left corner relatively simple since a logo badge is "
        "overlaid there."
    )
    prompt = (
        f"Using the exact product shown in the attached image, create a photorealistic, "
        f"commercial product-photography shot of \"{product_name}\" for a marketplace "
        f"listing — this is a paid advertising/catalog image meant to sell the product, "
        f"not a lifestyle or mood photo where the product happens to appear.{scene_hint} "
        f"{model_instruction} Preserve the product's exact shape, colors, materials, logo, "
        f"and details — do not redesign or alter it. "
        "The product is the hero of this shot and must dominate the frame: large, sharp, "
        "and in full crisp focus with every real detail (shape, texture, logo, color) "
        "clearly legible even at a glance — filling roughly half to two-thirds of the "
        "frame's height, the same way a real marketplace/e-commerce main listing photo "
        "(Shopee, Tokopedia, Amazon) frames its hero product, never small, distant, or "
        "lost as a minor detail in a wide environment shot. The environment provides real, "
        "believable context for where this product is used, but stays clearly secondary — "
        "it can be in slightly softer focus than the product itself and must never compete "
        "with or visually overpower it. Camera angle and framing should read as deliberate "
        "commercial product photography (eye-level or slight three-quarter angle, product "
        "fully visible and unobstructed), not a candid or randomly-cropped snapshot. "
        f"Sharp, crisp, {mood_instruction} The image MUST "
        "be a square 1:1 photo that fills the entire frame "
        "edge-to-edge with the photographed scene, with the full product (and person, if "
        "included) completely inside the frame — never cropped, cut off at the edges, or "
        "left blank/white/empty anywhere; the environment must continue naturally across "
        f"the whole square. {composition_instruction} No text, no logos, no watermarks, no UI "
        f"elements, no borders in the image itself.{brand_line}"
    )
    # Flatten onto white first — sending a raw RGBA cutout would show its
    # transparent areas as black once forced to RGB, confusing the model
    # about the product's actual edges.
    flattened = Image.new("RGB", cutout_photo.size, WHITE)
    flattened.paste(cutout_photo.convert("RGBA"), (0, 0), cutout_photo.convert("RGBA"))

    try:
        result_bytes = edit_image(prompt, flattened)
        return Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    except Exception:
        logger.exception("AI product scene generation failed for %s, falling back", product_name)
        return None


# How much of the top-left corner the real logo badge (pasted on top after
# generation) actually occupies, plus margin — the AI must keep this
# rectangle empty so its own headline/artwork never ends up hidden or
# clashing underneath the real logo. Deliberately generous (real badges
# measure noticeably smaller, see _framing_badge_extent_pct below) since
# being oversized here only costs the AI some placement freedom, with zero
# visual downside — unlike the deterministic patch panel below, this never
# actually gets painted onto the card.
_DEAD_ZONE_WIDTH_PCT = 0.55
_DEAD_ZONE_HEIGHT_PCT = 0.18


def _framing_badge_extent_pct(framing: str) -> tuple[float, float]:
    """How much of the top-left corner the framing's real logo badge shape
    actually covers (as a fraction of the card's width/height), measured
    off its real alpha pixels, same approach as _framing_safe_insets —
    used to size the deterministic dead-zone patch tightly to the real
    badge instead of the oversized fixed guess above. A flat-color patch
    noticeably bigger than the real badge shows up as its own visible
    smudge/box artifact wherever the badge doesn't actually cover it,
    especially against a brighter background. Recomputed from the framing
    image fresh on every call, no in-memory cache — so swapping a framing
    asset on disk takes effect on the very next generate.

    A higher alpha cutoff than _framing_safe_insets uses on purpose: this
    frame art has a faint, near-transparent drop-shadow line running the
    FULL width right under the top border (alpha ~10-40, invisible to the
    eye but very much > 10). That's harmless for the border-thickness
    measurement above, but here it would masquerade as "badge" content
    all the way to the half-width scan limit — a low bar like >10 alone
    made every single brand's badge measure as fully half the card wide,
    which isn't real. Genuine badge/border fill is solidly opaque
    (alpha > 200), so >80 cleanly separates real shape from shadow haze."""
    alpha = np.array(_load_framing_image(framing).getchannel("A")) > 80
    h, w = alpha.shape
    row_cov = alpha.mean(axis=1)

    def _extent(coverage: np.ndarray, threshold: float) -> int:
        limit = len(coverage) // 2
        last = 0
        for i in range(limit):
            if coverage[i] > threshold:
                last = i
        return last

    badge_h = _extent(row_cov, 0.06)
    # Column coverage measured only within the badge's own rows, not the
    # whole card height — otherwise the card's thin left border, which
    # runs the full height, would make the badge look full-height wide.
    # A higher threshold than the height pass: a bare 6% would still catch
    # the thin top border strip itself (present in every row of this crop,
    # so it forms its own low but non-zero baseline all the way across),
    # not just genuine badge columns.
    badge_rows = alpha[: badge_h + 1, :] if badge_h > 0 else alpha[:1, :]
    col_cov = badge_rows.mean(axis=0)
    badge_w = _extent(col_cov, 0.3)

    # +6 percentage points cushion on top of the real measured shape so the
    # patch fully covers the badge's own soft shadow/anti-aliased edge,
    # without being so oversized it shows as a smudge box beyond it.
    width_pct = min(0.7, badge_w / w + 0.06)
    height_pct = min(0.35, badge_h / h + 0.06)
    return (width_pct, height_pct)


def _patch_dead_zone(
    card: Image.Image, panel_color: tuple[int, int, int] = NAVY, framing: str = DEFAULT_FRAMING,
) -> None:
    """Cover the top-left corner reserved for the real logo badge (composited
    on top right after this runs) with a solid, deliberate color panel
    instead of trying to disguise whatever the AI scene model drew there.

    Earlier versions tried to hide that area instead of replacing it —
    first by cloning a patch from directly below the dead zone (which broke
    when the AI's own duplicated ghost text ran tall enough to contaminate
    the clone source too), then by heavily blurring the zone's own pixels
    in place (which destroyed text/artifacts fine, but still reads as a
    visibly lighter, hazy smudge against a sharper or moodier scene no
    matter how well its brightness is matched afterward — a blur is always
    a blur next to in-focus photo detail). A flat color panel has no such
    failure mode: it never depends on the AI having drawn anything
    reasonable there in the first place, so the result is identical and
    artifact-free on every single generation, and reads as an intentional
    brand color-block behind the logo rather than an accident."""
    w, h = card.size
    width_pct, height_pct = _framing_badge_extent_pct(framing)
    zone_w = round(w * width_pct)
    zone_h = round(h * height_pct)
    if zone_w <= 0 or zone_h <= 0:
        return

    panel = Image.new("RGBA", (zone_w, zone_h), panel_color + (255,))

    # Solid near the corner, fading out toward the zone's own right/bottom
    # edge so the panel blends into the surrounding photo instead of ending
    # in a hard-edged rectangle.
    mask = Image.new("L", (zone_w, zone_h), 255)
    mask_draw = ImageDraw.Draw(mask)
    fade = max(1, round(min(zone_w, zone_h) * 0.35))
    for y in range(zone_h - fade, zone_h):
        mask_draw.line([(0, y), (zone_w, y)], fill=round(255 * (zone_h - y) / fade))
    for x in range(zone_w - fade, zone_w):
        alpha = round(255 * (zone_w - x) / fade)
        existing = list(mask.crop((x, 0, x + 1, zone_h)).getdata())
        for y, current in enumerate(existing):
            mask.putpixel((x, y), min(current, alpha))

    card.paste(panel, (0, 0), mask)


def _frame_safe_zone_instruction(framing: str) -> str:
    """A prompt paragraph describing, in percentages of the frame, how much
    margin this specific framing's real border/tab artwork actually eats
    into each of the 4 edges — measured off its real pixels (same numbers
    the deterministic card composers use), not a fixed guess, since each
    brand's border is a different thickness (e.g. Ladder Bro's bottom tab
    is much taller than GOSAVE's thin edge). Used by the full-AI-design
    prompts so no text/badge/circle — and, critically, no part of the
    product itself — ends up partly hidden once the real frame is pasted
    on top afterward."""
    safe = _framing_safe_insets(framing)
    w, h = CARD_SIZE
    # +6 extra percentage points of cushion on top of the frame's own real
    # measured border, on every edge — the model's own placement has some
    # imprecision, and the raw measured border alone leaves zero room for
    # that; a product rendered exactly at the literal edge still risks
    # landing a few pixels under the frame once it's pasted on top. Bumped
    # up from 3 after varian cards kept landing text/product right at the
    # edge of the safe zone — the model treats the margin as a target to
    # hug rather than a hard limit, so a bigger cushion is needed to keep
    # the actual result clear of the frame in practice.
    buffer_pct = 6
    top_pct = round(safe["top"] / h * 100) + buffer_pct
    bottom_pct = round(safe["bottom"] / h * 100) + buffer_pct
    left_pct = round(safe["left"] / w * 100) + buffer_pct
    right_pct = round(safe["right"] / w * 100) + buffer_pct
    return (
        f"This brand's decorative border/frame artwork (and, along the bottom edge for some "
        f"brands, a colored tab) is pasted on top of your finished image afterward, running "
        f"along all four edges of the square. Keep every piece of text, badge, numbered "
        f"circle, icon, AND the complete product itself fully inside the safe interior area "
        f"— at least {top_pct}% of the frame's height from the top edge, {bottom_pct}% from "
        f"the bottom edge, {left_pct}% of its width from the left edge, and {right_pct}% "
        f"from the right edge. These margins already include extra safety cushion on top of "
        f"the frame's own real border thickness — treat them as a hard boundary, not a "
        f"target to hug. The product must never touch, cross, run under, or get cropped by "
        f"that outer border, not even by a few pixels — treat the safe interior area as the "
        f"actual usable canvas for the product and size/position it comfortably within those "
        f"bounds, the same way a professional e-commerce listing photo keeps its product "
        f"fully clear of any frame or watermark overlay. When in doubt, render the product "
        f"slightly smaller with more clearance rather than risk any part of it landing under "
        f"the border. Only the plain background/environment itself (empty scenery, no "
        f"product, no text) may extend into that outer border area, since it gets cleanly "
        f"covered — nothing that needs to stay visible or recognizable may end up partly "
        f"hidden under the frame."
    )


def _default_scene_hint(prefix: str = "Background environment") -> str:
    """Fallback scene wording used only when there's no AI-derived or
    user-typed scene_description at all — the normal path is that
    scene_description already comes from a per-product, category-aware
    BACKGROUND_SCENE/SCENE_i field (see generate_keypoints /
    generate_usage_data / generate_keunggulan_content), so this generic
    text is a last resort, not the common case."""
    return (
        f" {prefix}: a clean, uncluttered, professionally lit setting deliberately chosen to "
        f"match this exact product's real category and everyday use — the way a professional "
        f"art director would pick a location for this specific product's shoot, never a "
        f"generic, random, or mismatched backdrop."
    )


def _background_mood_instruction(framing: str) -> str:
    """Whether a card's photographic background should default to a dark,
    dramatic mood or a bright, clean one — driven by the brand's own
    character (see BRAND_STYLE_HINTS), never a hardcoded blanket choice.
    GOTO is deliberately cute/playful/bright (see brand_style_hint); every
    other current brand leans fierce/dramatic safety-gear energy. A
    hardcoded "dark, moody" background instruction directly fights GOTO's
    own brand-mood hint elsewhere in the same prompt, producing a card
    that reads as generically dark/serious instead of matching that
    brand's actual look."""
    if framing == "goto":
        return (
            "A bright, clean, warm environment matching that real-world use and this "
            "brand's playful, friendly character (see the brand mood described above) — "
            "soft, even, cheerful daylight, tones the white/bright headline text stays "
            "highly legible against."
        )
    return (
        "A dark, moody, dramatically lit environment matching that real-world use and "
        "this brand's character (see the brand mood described above) — deep, softly "
        "blurred tones so the white/bright headline text stays highly legible."
    )


def _product_positioning_instruction() -> str:
    """A prompt paragraph shared by every full-AI-design card type, tackling
    two specific recurring quality problems: the product rendered too
    large/dominant for a tidy marketplace catalog shot, and the product
    propped up in a nonsensical, unprofessional way (e.g. a harness looped
    around a random pole/scaffolding bar like debris, instead of shown the
    way an actual e-commerce listing photo would present it)."""
    return (
        f"PRODUCT SIZE & POSITIONING\n"
        f"Size the product the way a professional marketplace catalog photo would, never "
        f"oversized or stretched to dominate every inch of its space — it should read as a "
        f"neatly proportioned, ideally-sized product shot, with the same comfortable margin "
        f"around it a real Shopee/Tokopedia/Amazon main listing photo has, not a close-up "
        f"crop or an artificially inflated hero shot. "
        f"The way the product is propped up or held must make real-world sense for that "
        f"exact type of product and look deliberate and professional, the way an actual "
        f"e-commerce product photographer would stage it — for example: a wearable item "
        f"(harness, vest, belt, helmet) shown worn on a mannequin/dress form or a person, or "
        f"neatly laid flat / mounted on a clean display hook; a handheld tool shown held "
        f"naturally in a hand or resting on a clean surface; a flat or boxed item shown "
        f"standing upright or laid flat. Never drape, loop, sling, or hang the product "
        f"around a random pole, scaffolding bar, railing, beam, or any incidental object "
        f"purely because one appears in the background scene — that reads as sloppy debris, "
        f"not a real product photo, even if the background scene is a construction site. If "
        f"nothing in the scene offers a genuinely natural way to display the product, show "
        f"it on a plain stand, clean surface, or worn by a person/mannequin instead of "
        f"forcing it onto whatever object happens to be nearby."
    )


def _ecommerce_readability_instruction() -> str:
    """A prompt paragraph shared by every full-AI-design card type, asking
    for the specific kind of visual clarity a marketplace/e-commerce
    listing image needs — every word instantly legible and the background
    read as clean and intentional, never a blurry or ambiguous mess a
    shopper has to squint at."""
    return (
        f"READABILITY & POLISH\n"
        f"Every word of every headline, label, and caption must be instantly legible at a "
        f"glance, at both full size and thumbnail size — strong, clean contrast between the "
        f"text and whatever sits directly behind it. Achieve that ONLY with a soft drop "
        f"shadow directly on the letters themselves, and/or a very gradual, edgeless "
        f"darkening of the photo itself that fades smoothly outward with no visible border "
        f"— NEVER a rectangle, rounded-rectangle, card, plaque, panel, box, or any other "
        f"shape with a defined edge/outline placed behind a text zone; the background must "
        f"always read as one continuous, uninterrupted photo, never a photo with a solid or "
        f"semi-transparent box stuck on top of it. If a background area is too busy for text "
        f"to sit on, blur or darken that region of the photo itself smoothly rather than "
        f"covering it with any kind of shape. Every letterform must be crisp, "
        f"sharp, fully-formed, and correctly spelled exactly as given — never blurry, smudged, "
        f"warped, overlapping, half-formed, or garbled the way image models sometimes render "
        f"text; if a piece of text can't be rendered cleanly and correctly, keep it simple "
        f"(shorter line breaks, slightly smaller size) rather than let it come out mangled. "
        f"One consistent, modern sans-serif typeface across the entire card — never mix "
        f"multiple different typefaces or lettering styles. The background must always read "
        f"as clean, deliberate, and in-focus where it matters (never so blurry, dark, noisy, "
        f"or ambiguous that it looks like a mistake or a low-quality photo) while still "
        f"staying visually secondary to the product and text.\n\n"
        f"NO INVENTED ELEMENTS\n"
        f"Do not invent, add, or hallucinate any extra badge, sticker, seal, stamp, ribbon, "
        f"logo, watermark, icon, shape, pattern, or decorative graphic anywhere on the card "
        f"— on the background, floating in empty space, or attached to the product — beyond "
        f"exactly what this prompt explicitly asks for. The background itself must stay a "
        f"plain, believable environment/scene only: no random circles, blobs, geometric "
        f"shapes, texture overlays, or odd unexplained objects floating in it. If in doubt, "
        f"leave that area empty rather than filling it with something not requested here. No "
        f"visual clutter — no stray shapes, duplicate elements, random extra icons, or "
        f"unexplained objects anywhere on the card. The end result must look like a "
        f"finished, professional marketplace listing image, not a rough draft or a busy "
        f"collage."
    )


def _keypoint_title_style_text(framing: str, accent_hex: str) -> str:
    """Title color/treatment text for the keypoint card's TYPOGRAPHY section
    — framing-specific because GOTO's real approved reference uses a totally
    different bold-black-with-white-outline comic/streetwear title instead
    of GOSAVE's metallic gold-foil corporate title; hardcoding the corporate
    version for every brand would fight against whichever reference image
    actually got attached for that brand."""
    if framing == "goto":
        return (
            f"The title in bold black fill with a clean white outline stroke around each "
            f"letter, playful bold rounded sans-serif — matching the reference image's own "
            f"bold comic/streetwear title treatment exactly, not a corporate metallic look. "
            f"{accent_hex} for subtitle. Every character spelled EXACTLY as given above, no "
            f"typos, no extra or missing letters."
        )
    return (
        f"The FIRST line of the title in plain white. Every line AFTER the first styled with "
        f"a premium metallic foil-gradient fill in {accent_hex} tones (lighter highlight "
        f"catching the upper-left of each letter, deepening toward the lower-right, like "
        f"brushed gold/metal foil catching light) — matching the reference image's own "
        f"two-tone title treatment exactly, not a flat solid color. {accent_hex} for "
        f"subtitle. Modern minimal design. Every character spelled EXACTLY as given above, "
        f"no typos, no extra or missing letters."
    )


def _keypoint_badge_style_text(framing: str, primary_hex: str, accent_hex: str) -> str:
    """Feature-badge shape/color text — see _keypoint_title_style_text for
    why this is framing-specific: GOTO's reference uses a black rounded-pill
    badge (icon circle + label text inside one long pill), not GOSAVE's
    navy circle with a glowing accent ring."""
    if framing == "goto":
        return (
            f"Matching the reference image's own badges exactly — this is the single most "
            f"important style detail on the whole card, copy it precisely. Each badge is one "
            f"long solid black rounded-pill shape (fully rounded ends), with a small white "
            f"circle containing the icon on the pill's left end, and the label text in bold "
            f"white sitting inside the same pill to the icon's right. No glow, no gradient, "
            f"no ring outline — flat solid black pill only. Absolutely no number, digit, or "
            f"step indicator anywhere on, in, or beside any badge."
        )
    return (
        f"Matching the reference image's own badges exactly — this is the single most "
        f"important style detail on the whole card, copy it precisely rather than "
        f"defaulting to a generic circle. A dark navy {primary_hex} filled circle with a "
        f"thin, crisp {accent_hex} ring border (not a soft blue glass gradient), a subtle "
        f"soft {accent_hex} glow bleeding gently outward past the ring, and a short thin "
        f"{accent_hex} underline sitting just beneath the label text next to it. Absolutely "
        f"no number, digit, or step indicator (no \"1\", \"2\", \"3\"...) anywhere on, in, "
        f"or beside any badge — a badge contains only its icon, nothing else."
    )


def _keypoint_icon_style_text(framing: str, accent_hex: str) -> str:
    if framing == "goto":
        return (
            f"Minimal thin OUTLINE/stroke line icons only, black stroke color (sitting on "
            f"the badge's small white icon circle, not directly on the black pill). "
            f"Consistent icon family across all badges. Professional vector style. Centered "
            f"perfectly. Modestly sized with generous padding."
        )
    return (
        f"Minimal thin OUTLINE/stroke line icons only (like Feather Icons or Material "
        f"Symbols \"outlined\" style, a slender 1.5-2px stroke) — NOT bold, thick, or fully-"
        f"filled glyphs. Consistent icon family across all badges. Professional vector "
        f"style. Centered perfectly. {accent_hex} icon color, matching the ring. Modestly "
        f"sized with generous padding — the icon itself spans roughly 40-45% of the badge "
        f"circle's diameter, clearly not touching or crowding the circle's inner edge."
    )


def generate_ai_designed_keypoint_card(
    cutout_photo: Image.Image, product_name: str, tagline: str, keypoints: list[str],
    scene_description: str, palette: str = DEFAULT_PALETTE, framing: str = DEFAULT_FRAMING,
    extra_instruction: str = "",
) -> Image.Image | None:
    """The whole keypoint card — background, product shot, logo badge,
    headline typography, and the 3 feature badges/icons — generated as one
    single AI image, instead of the deterministic PIL-compositing path
    (compose_keypoint_card). A hand-assembled circle-plus-flat-icon badge
    can only ever look like exactly that; a real image model asked to design
    the whole poster at once produces the organic gradients, natural badge
    integration, and varied composition an actual designer would, which is
    what a from-scratch AI render can do that piece-by-piece compositing
    fundamentally can't.

    Trade-off callers must know about: because the headline/tagline/keypoint
    TEXT is now drawn by the image model itself rather than deterministic
    PIL text rendering, it can occasionally misspell a word (the model is
    drawing letterforms, not typesetting a string) — this is not a bug to
    "fix", it's the inherent cost of this path vs. compose_keypoint_card's
    typo-proof-but-flatter rendering. Callers/users should treat the result
    as a draft that needs a quick proofread before publishing, not a
    guaranteed-correct final asset."""
    theme = _theme_colors(palette, True)
    primary_hex = "#%02x%02x%02x" % theme["primary"]
    accent_hex = "#%02x%02x%02x" % theme["accent"]
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    scene_hint = (
        f" Background environment, deliberately matching this product's own theme/category "
        f"(kept clean, simple, and uncluttered above all else): {scene_description}."
        if scene_description else _default_scene_hint()
    )
    real_keypoints = [kp for kp in keypoints if kp]
    safe_zone_line = _frame_safe_zone_instruction(framing)
    style_ref_line = _style_reference_instruction("keypoint", framing)

    subtitle_line = (
        f"\n\nSubtitle: one line, reading exactly \"{tagline}\" — spell only that text, do "
        f"NOT render any hex code, color name, or other instruction text on the card, only "
        f"the quoted subtitle words above. Style it in the hex color {accent_hex}."
        if tagline else ""
    )
    prompt = (
        f"Create a premium commercial product advertisement for a {_brand_category_label(framing)} "
        f"brand.{brand_line}{style_ref_line}\n\n"
        f"STYLE\n"
        f"Modern, premium, clean, corporate branding. Inspired by {_style_benchmark(framing)} "
        f"product advertisements.\n\n"
        f"LAYOUT\n"
        f"Square 1:1 social media poster.\n\n"
        f"{safe_zone_line}\n\n"
        f"COMPOSITION SAFETY\n"
        f"Keep the complete product silhouette fully visible with comfortable negative space "
        f"around it. Do not crop, trim, hide, or let any part of the product, headline, "
        f"badge, icon, label, or subtitle touch the outer edge of the square. Leave at "
        f"least 6% clear breathing room around the hero product and all text groups, in "
        f"addition to the brand-frame safe area above. If the layout feels crowded, make "
        f"the product and typography slightly smaller rather than pushing anything off "
        f"canvas.\n\n"
        f"{_product_positioning_instruction()}\n\n"
        f"{_ecommerce_readability_instruction()}\n\n"
        f"Top-left ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of height, "
        f"measured from the very corner): render this rectangle as pure continuation of the "
        f"background/product photo itself — same scene, same blur, same exposure as the rest "
        f"of that photo. Do NOT draw any logo, badge, wordmark, text, or shape there — and "
        f"just as importantly, do NOT draw any plain white/light card, plaque, panel, sign, "
        f"or blank rectangle there either, even as a placeholder or empty design element. It "
        f"must look like an untouched crop of the photo, not a reserved empty box. CRITICAL: "
        f"this also means no duplicate, cropped, or partial second copy of the headline/"
        f"title text (or any other text on this card) may bleed into or peek out of this "
        f"rectangle — every piece of text on the card is drawn exactly once, at its own "
        f"correct position elsewhere, never echoed or restarted here. A real "
        f"brand logo badge graphic gets composited there afterward at those exact pixels, "
        f"fully covering whatever is drawn there — but only a plain photo patch composites "
        f"cleanly under it; a light-colored placeholder shape shows through as a visible "
        f"mismatched edge around the logo.\n\n"
        f"Center:\n"
        f"The exact product shown in the FIRST attached image (the real product photo) is "
        f"the main hero, framed "
        f"the way a real marketplace/e-commerce listing photo (Shopee, Tokopedia, Amazon) "
        f"frames its main product shot: large and unmistakably the focal point, comfortably "
        f"filling roughly half to two-thirds of the frame's height — never so large it "
        f"crowds into the right-side headline/feature-badge column or the safe-zone margins, "
        f"and never so small it looks lost or like an afterthought. POSITIONING matters — "
        f"place it in whichever natural resting position best shows off the whole product "
        f"(standing upright, neatly laid down, or hung straight from its own strap/hook), "
        f"level and upright, not tilted or floating at a random awkward angle, with the "
        f"complete product visible, never cropped or cut off by the frame edge. Ultra "
        f"realistic product photography. Must match the FIRST attached image (the real "
        f"product photo) exactly — same shape, same colors, same materials/textures, same "
        f"logo and every printed label/text on it, same proportions between its parts — "
        f"with every single part and component fully present, including every small attached "
        f"part (straps, laces, cords, buckles, zippers, stitching, hanging tags, or any other "
        f"small accessory attached to the product) — none of these may be omitted, "
        f"shortened, simplified, merged together, or redesigned even slightly just because "
        f"they're small. The "
        f"product must appear completely by itself: no person, hand, model, toy, or any "
        f"other object next to, holding, or wearing it — only the product alone. Natural "
        f"realistic shadow. Soft reflection on wet/glossy floor if applicable. Cinematic "
        f"lighting. Hyper-detailed, high-resolution texture — every stitch, seam, grain, and "
        f"surface detail crisp and clearly visible, never smoothed-over, plastic-looking, or "
        f"low-detail. Razor-sharp, perfectly in-focus product, absolutely no blur, softness, "
        f"or motion blur on it — background in "
        f"a gentle shallow depth of field.{scene_hint}\n\n"
        f"Background:\n"
        f"Professional environment matching the description above, but always kept clean, "
        f"simple, and uncluttered above everything else — minimal visual noise, no chaotic "
        f"jumble of objects/shapes/signage competing for attention. Shallow depth of field, "
        f"background softly blurred so it clearly reads as secondary to the product. Clean "
        f"composition, luxury commercial photography. Default to bright, clean daylight "
        f"(soft golden-hour sun or bright even daytime/overcast light) unless the "
        f"description above explicitly calls for a darker/night/moody mood — whatever the "
        f"mood, the scene must always read clearly and intentionally lit, never accidentally "
        f"underexposed or murky.\n\n"
        f"TYPOGRAPHY\n"
        f"Modern premium sans-serif typography, inspired by Helvetica Neue, Gotham, DIN, "
        f"Montserrat ExtraBold. Large bold title. Excellent letter spacing. Clean hierarchy. "
        f"No outline stroke. Soft natural shadow only. Professional kerning. Corporate "
        f"advertising layout. POSITION: top-right area of the poster, starting near the top "
        f"edge (below the reserved top-left rectangle's height, but the headline itself "
        f"stays on the right side at that same top height) — entirely within the right "
        f"{100 - round(_DEAD_ZONE_WIDTH_PCT*100)}% of the frame's width, right-aligned as one "
        f"tidy block. CRITICAL — check this for EVERY line of the title individually: no "
        f"character of any line may ever cross the horizontal center of the image or come "
        f"anywhere near the reserved top-left rectangle, even the widest/longest line. A "
        f"long product name is common and expected — when it doesn't comfortably fit at a "
        f"large size, you MUST wrap it across more lines (3, even 4 if genuinely needed, one "
        f"natural word-group per line) AND shrink the font size, checking after each change "
        f"that every single line still clears the boundary — a title that stays large but "
        f"bleeds into the reserved rectangle or crosses the center is a failed result, worse "
        f"than a smaller, fully-compliant title.\n\n"
        f"Title (exact text, spelled EXACTLY as given below, word for word, no typos, no "
        f"extra or missing letters, and — this matters most — no repeated or duplicated "
        f"word anywhere; this text appears on the card exactly ONCE, never twice, never "
        f"with any word or line echoed again before or after it):\n\"{product_name}\""
        f"{subtitle_line}\n\n"
        f"Text color:\n{_keypoint_title_style_text(framing, accent_hex)}\n\n"
        f"RIGHT SIDE FEATURE SECTION\n\n"
        f"POSITION: in the right portion of the frame, directly below the headline block. "
        f"Exactly {len(real_keypoints)} rows stacked in a single VERTICAL list running "
        f"straight down toward the bottom of the frame — one row above the next, never "
        f"placed to the left of the product. Each row is its own small circular icon badge "
        f"on the left of that row, with its text label sitting immediately to the RIGHT of "
        f"that same circle (not above it, not below it) — icon and its label always sit "
        f"side by side as one horizontal pair, vertically centered on each other. Rows are "
        f"evenly spaced with comfortable breathing room between them, never touching or "
        f"crowding each other or the product.\n\n"
        f"Badge style:\n{_keypoint_badge_style_text(framing, primary_hex, accent_hex)}\n\n"
        f"Icons:\n{_keypoint_icon_style_text(framing, accent_hex)}\n\n"
        f"One row per bullet below, listed top to bottom — each icon must be the single "
        f"most obvious, literal visual symbol for that SAME bullet's own label beside it "
        f"(icon and label must always be the matching pair listed together here, never "
        f"mixed up with another bullet's icon or label). None of this — not a number, not "
        f"a bullet mark, not any part of this list's own formatting — is itself something "
        f"to render on the card; only the icon shape and the label text appear:\n"
        + "\n".join(
            f"- icon = the clearest possible symbol for \"{kp}\"; "
            f"label to its right, spelled exactly = \"{kp}\""
            for kp in real_keypoints
        ) + "\n\n"
        f"Typography:\n"
        f"SemiBold. White text. Left-aligned, vertically centered against the circle "
        f"beside it (same row, not above or below). Comfortable spacing. No bullet. Modern "
        f"corporate style. No typos, no extra or missing letters in any label.\n\n"
        f"COLOR PALETTE\n"
        f"{primary_hex} (corporate blue), {accent_hex} (brand accent), white, dark gray.\n\n"
        f"LIGHTING\n"
        f"Cinematic lighting. Soft rim light. Ambient light. Global illumination. Realistic "
        f"reflections. Photorealistic.\n\n"
        f"QUALITY\n"
        f"Award-winning advertising. Luxury commercial photography. Professional product "
        f"campaign. Ultra realistic. Hyper detailed. 8K. Extremely sharp. No clutter. "
        f"Minimal. Premium. The image must fill the entire square frame edge to edge — no "
        f"borders, no blank margins, nothing cropped off. No watermarks, no UI chrome, no "
        f"placeholder text anywhere other than the exact strings specified above."
    )

    if extra_instruction.strip():
        prompt += (
            f"\n\nADDITIONAL USER INSTRUCTION (apply on top of everything above, without "
            f"breaking any of the layout/safety rules already specified — and without "
            f"loosening product accuracy: the product must still match the attached "
            f"reference photo exactly in shape/color/material/every detail, regardless of "
            f"what this instruction asks for): \"{extra_instruction.strip()}\""
        )

    try:
        result_bytes = _generate_designed_card_image(prompt, cutout_photo, "keypoint", framing)
        card = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        # The real brand frame/logo badge — the actual asset, pixel-exact,
        # not the AI's own re-drawing of it (which risked a slightly-off
        # logo, wrong proportions, or misspelling the wordmark) — pasted on
        # top last, same as every other card type. Resized to the fixed
        # card size first since the model's square output isn't guaranteed
        # to land on that exact pixel resolution.
        if card.size != CARD_SIZE:
            card = _fit_on_blurred_canvas(card, CARD_SIZE)
        _patch_dead_zone(card, theme["primary"], framing)
        card.alpha_composite(_load_framing_image(framing))
        return card
    except Exception:
        logger.exception("AI full-design keypoint card generation failed for %s", product_name)
        return None


def generate_ai_designed_keunggulan_card(
    cutout_photo: Image.Image, product_name: str, headline: str, emphasis: str, points: list[str],
    scene_description: str, palette: str = DEFAULT_PALETTE, framing: str = DEFAULT_FRAMING,
    extra_instruction: str = "",
    custom_primary: str | None = None, custom_accent: str | None = None,
) -> Image.Image | None:
    """One "Fitur Keunggulan" poster — a bold headline (its key phrase in the
    accent color) over a dramatic close-up hero shot, with exactly 3 glowing
    icon-badge + text rows stacked underneath it — generated as one AI
    image, styled off assets/fitur unggulan.png (the brand-approved
    reference: headline top-left, 3 icon rows below it on the left, product
    close-up filling the right side). Callers generate one of these per
    selected theme (1-5 per batch, see generate_keunggulan_content), each
    with its own headline/points/scene so a multi-image batch reads as
    distinct highlights, not repeated copies of the same card. This card
    type is always AI-full-design — there's no deterministic PIL-compose
    fallback, same proofread-before-publish trade-off as the other
    full-design cards."""
    theme = _theme_colors(palette, True, custom_primary, custom_accent)
    primary_hex = "#%02x%02x%02x" % theme["primary"]
    accent_hex = "#%02x%02x%02x" % theme["accent"]
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    scene_hint = (
        f" {scene_description}." if scene_description else
        " A dramatic, tightly-zoomed macro close-up on the part of the product that best "
        "shows this overall theme, with the rest of the product extending past the frame "
        "edge rather than being shrunk down to fit fully inside it."
    )
    safe_zone_line = _frame_safe_zone_instruction(framing)
    style_ref_line = _style_reference_instruction("keunggulan", framing)
    emphasis_line = (
        f"\n\nWithin that headline, the exact phrase \"{emphasis}\" must be colored {accent_hex} "
        f"— every other word stays white."
        if emphasis and emphasis in headline else ""
    )
    real_points = [p for p in points if p][:3]

    prompt = (
        f"Create a premium commercial product-advantage advertisement for a "
        f"{_brand_category_label(framing)} brand.{brand_line}{style_ref_line}\n\n"
        f"STYLE\n"
        f"Modern, premium, dramatic, corporate branding. Inspired by {_style_benchmark(framing)} "
        f"product advertisements.\n\n"
        f"LAYOUT\n"
        f"Square 1:1 social media poster. This image is about ONE overall product-advantage "
        f"theme, backed by {len(real_points)} short supporting points — not a general product "
        f"catalog shot.\n\n"
        f"{safe_zone_line}\n\n"
        f"{_ecommerce_readability_instruction()}\n\n"
        f"Top-left ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of height, "
        f"measured from the very corner): render this rectangle as pure continuation of the "
        f"background/product photo itself — same scene, same blur, same exposure as the rest "
        f"of that photo. Do NOT draw any logo, badge, wordmark, text, or shape there — and "
        f"just as importantly, do NOT draw any plain white/light card, plaque, panel, sign, "
        f"or blank rectangle there either, even as a placeholder or empty design element. A "
        f"real brand logo badge graphic gets composited there afterward at those exact pixels.\n\n"
        f"Hero (right side of frame):\n"
        f"The exact product shown in the FIRST attached image (the real product photo), as a "
        f"large, dramatic, tightly-zoomed macro hero shot filling most of the right side of "
        f"the frame — like the SECOND attached image's example, which crops in tight on one "
        f"detail of ITS OWN product rather than showing the whole thing small and centered "
        f"(copy that cropping/zoom STYLE only, never that example's actual product). Zoom in "
        f"aggressively on the specific part/detail of the FIRST image's product that proves "
        f"this overall theme; it is fine, expected, and encouraged for the rest of the "
        f"product to extend past the top/side/bottom edge of the frame, exactly like the "
        f"second image's example does — do NOT shrink the product down to keep the whole "
        f"thing inside the frame, that reads as flat and generic instead of a premium "
        f"dramatic ad shot. Only the featured detail/part itself must stay fully visible and "
        f"in sharp focus. Every part that IS shown must be pixel-accurate to the FIRST "
        f"attached image — exact real shape, color, material, texture, logo, and proportions "
        f"— including any small attached part visible in that crop (straps, laces, cords, "
        f"buckles, zippers, stitching, hanging tags, or any other small accessory), rendered "
        f"in full, never omitted or simplified just because it's small, with zero "
        f"redesigning, zero substituting a similar-looking product, and zero "
        f"blending in any detail from the second (style-only) reference image. The product "
        f"must appear completely "
        f"by itself: no person, hand, model, toy, or any other object next to, holding, or "
        f"wearing it — only the product alone. Ultra realistic product photography, "
        f"hyper-detailed high-resolution texture — every stitch, seam, grain, and surface "
        f"detail crisp and clearly visible, never smoothed-over or low-detail — razor-sharp, "
        f"perfectly in-focus, absolutely no blur or softness on it, cinematic lighting, "
        f"natural shadow, soft "
        f"reflection on a wet/glossy surface if applicable.{scene_hint}\n\n"
        f"Background:\n"
        f"The rest of the frame (mostly the left side, behind the headline and point rows) is "
        f"{_background_mood_instruction(framing)} "
        f"Keep it clean, simple, and uncluttered above everything else: minimal visual noise, "
        f"no chaotic jumble of shapes/objects. Shallow depth of field, luxury commercial "
        f"photography.\n\n"
        f"TYPOGRAPHY (HEADLINE)\n"
        f"Modern premium sans-serif, inspired by Helvetica Neue, Gotham, DIN, Montserrat "
        f"ExtraBold. POSITION: upper-left area of the poster, below the reserved top-left "
        f"rectangle, left-aligned, wrapping naturally across 2-3 short lines — large, bold, "
        f"confident, taking up meaningful vertical space, entirely within the left half of the "
        f"frame.\n\n"
        f"Headline (exact text, spelled EXACTLY as given, no typos, no extra or missing "
        f"letters, no word or line repeated/duplicated anywhere — this text appears exactly "
        f"ONCE on the card):\n\"{headline}\"\n"
        f"Color: white.{emphasis_line}\n\n"
        f"LEFT SIDE SUPPORTING-POINT ROWS\n\n"
        f"POSITION: directly below the headline, left-aligned to the same left margin as the "
        f"headline. Exactly {len(real_points)} rows stacked in a single vertical list, one row "
        f"above the next, running down toward the bottom-left of the frame — never placed to "
        f"the right of the headline or overlapping the product. Each row is its own small "
        f"circular icon badge on the left of that row, with its point text sitting immediately "
        f"to the RIGHT of that same circle (not above it, not below it) — icon and its text "
        f"always sit side by side as one horizontal pair, vertically centered against each "
        f"other, the text wrapping across 2-3 short lines if needed. Rows are evenly spaced "
        f"with comfortable breathing room between them, never touching or crowding each other.\n\n"
        f"Badge style:\n"
        f"Premium glowing glass-like circle, matching the reference image's own badges "
        f"exactly — this is the single most important style detail on the whole card, copy it "
        f"precisely rather than defaulting to a plain flat circle. Deep corporate blue "
        f"{primary_hex} radial gradient fill (subtly lighter toward the upper-left, deepening "
        f"toward the opposite edge — a glossy sphere, not one flat tone), a soft glass "
        f"highlight crescent across the upper portion, a gentle drop shadow beneath the circle "
        f"for depth, and — most importantly — a vivid, saturated electric-blue glow that "
        f"bleeds softly outward past the circle's own edge, brightest as a rim-light hugging "
        f"the top arc of the circle and fading lower down, like a backlit LED badge at night. "
        f"The ring/edge of the circle itself is that same vivid electric blue, not plain "
        f"white.\n\n"
        f"Icons:\n"
        f"Minimal thin OUTLINE/stroke line icons only (like Feather Icons or Material Symbols "
        f"\"outlined\" style, a slender 1.5-2px stroke) — NOT bold, thick, or fully-filled "
        f"glyphs. Consistent icon family across all badges. Professional vector style. "
        f"Centered perfectly. White icon. Modestly sized with generous padding — the icon "
        f"itself spans roughly 40-45% of the badge circle's diameter, clearly not touching or "
        f"crowding the circle's inner edge.\n\n"
        f"One row per point below, listed top to bottom — each icon must be the single most "
        f"obvious, literal visual symbol for that SAME row's own point text beside it (icon and "
        f"text must always be the matching pair listed together here, never mixed up with "
        f"another row's icon or text). Nothing but the icon shape and the point text appear in "
        f"each row — no number, no bullet mark:\n"
        + "\n".join(
            f"- icon = the clearest possible symbol for \"{point}\"; "
            f"text to its right, spelled exactly = \"{point}\""
            for point in real_points
        ) + "\n\n"
        f"Point text typography:\n"
        f"SemiBold. White text. Left-aligned, vertically centered against the circle beside it "
        f"(same row, not above or below). Comfortable spacing. No bullet. Modern corporate "
        f"style. No typos, no extra or missing letters in any point.\n\n"
        f"COLOR PALETTE\n"
        f"{primary_hex} (corporate blue), {accent_hex} (brand accent), white, dark charcoal.\n\n"
        f"LIGHTING\n"
        f"Cinematic lighting. Soft rim light. Ambient light. Global illumination. Realistic "
        f"reflections. Photorealistic.\n\n"
        f"QUALITY\n"
        f"Award-winning advertising. Luxury commercial photography. Professional product "
        f"campaign. Ultra realistic. Hyper detailed. 8K. Extremely sharp. No clutter. Minimal. "
        f"Premium. The image must fill the entire square frame edge to edge — no borders, no "
        f"blank margins, nothing cropped off. No watermarks, no UI chrome, no placeholder text "
        f"anywhere other than the exact strings specified above."
    )

    if extra_instruction.strip():
        prompt += (
            f"\n\nADDITIONAL USER INSTRUCTION (apply on top of everything above, without "
            f"breaking any of the layout/safety rules already specified — and without "
            f"loosening product accuracy: the product must still match the attached "
            f"reference photo exactly in shape/color/material/every detail, regardless of "
            f"what this instruction asks for): \"{extra_instruction.strip()}\""
        )

    try:
        result_bytes = _generate_designed_card_image(prompt, cutout_photo, "keunggulan", framing)
        card = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        if card.size != CARD_SIZE:
            card = _fit_on_blurred_canvas(card, CARD_SIZE)
        _patch_dead_zone(card, theme["primary"], framing)
        card.alpha_composite(_load_framing_image(framing))
        return card
    except Exception:
        logger.exception("AI keunggulan card generation failed for %s", product_name)
        return None


def generate_ai_designed_varian_card(
    cutout_photo: Image.Image, product_name: str, variant_name: str,
    palette: str = DEFAULT_PALETTE, framing: str = DEFAULT_FRAMING,
    extra_instruction: str = "",
    custom_primary: str | None = None, custom_accent: str | None = None,
    scene_description: str | None = None,
) -> Image.Image | None:
    """One "Varian" poster for a single user-uploaded variant reference
    photo — a clean hero shot of THAT variant's real photo (the exact
    color/size/material it actually is, never guessed or invented) with a
    simple text label naming the variant. Unlike every other card type
    here, there is no AI-written copy to generate (no tagline, no
    keypoints, no scene) — the whole point, per the user's own request, is
    accuracy: showing precisely what was uploaded, not an AI's best guess
    at what a variant might look like. Callers generate one of these per
    uploaded variant photo (see list_variant_photos), so a batch of
    several photos under the same or different names each becomes its own
    card, labeled with that photo's own variant name."""
    theme = _theme_colors(palette, True, custom_primary, custom_accent)
    primary_hex = "#%02x%02x%02x" % theme["primary"]
    accent_hex = "#%02x%02x%02x" % theme["accent"]
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    safe_zone_line = _frame_safe_zone_instruction(framing)
    style_ref_line = _style_reference_instruction("varian", framing)
    safe_name = variant_name.strip() or "Varian"
    safe_product = product_name.strip() or "Produk"

    prompt = (
        f"Create a premium commercial product-variant showcase image for a "
        f"{_brand_category_label(framing)} brand.{brand_line}{style_ref_line}\n\n"
        f"NON-NEGOTIABLE: the product itself must be reproduced completely unchanged from "
        f"the FIRST attached image — same exact shape, color, material, texture, pattern, "
        f"proportions, and every visible detail, down to small attached parts. You are only "
        f"placing that unchanged product into a new background/scene with a headline on top "
        f"— not redesigning, restyling, recoloring, or reinterpreting the product in any way. "
        f"This also means never \"improving\" it: no retouching, no smoothing over or "
        f"removing scuffs/dust/imperfections/wear that are actually visible on it, no "
        f"brightening or idealizing its color beyond a normal lighting change, no "
        f"straightening or reshaping it, no completing or cleaning up a partially-worn "
        f"label/logo/print — reproduce it exactly as-is, flaws included if any are visible. "
        f"Equally, never remove, omit, crop out, shrink away, or simplify any part or detail "
        f"of the product that's visible in the reference — everything that's there must stay "
        f"there, in full. The only thing allowed to change is the surrounding scene, "
        f"lighting, and camera angle — never the product itself. If nothing else in this "
        f"prompt is followed precisely, this rule still must be.\n\n"
        f"STYLE\n"
        f"Modern, premium, dramatic commercial product photography, matching the reference "
        f"image's own mood exactly (large dominant hero shot, dark moody environmental "
        f"background, bold top headline). Inspired by {_style_benchmark(framing)} product "
        f"advertisements.\n\n"
        f"LAYOUT\n"
        f"Square 1:1 social media poster. This image showcases ONE specific product variant "
        f"— a large, tall hero shot of the exact product shown in the FIRST attached image, "
        f"centered or slightly offset, echoing the reference image's own generous product "
        f"scale STYLE only (never that reference's own product) but WITHOUT copying its "
        f"product size literally — the reference was framed differently and its product may "
        f"sit closer to the edges than what's safe here. The whole product, and this whole "
        f"variant's distinguishing look, must be clearly, fully visible — not a tight macro "
        f"crop — but sized so there is comfortable, visible empty space between every edge "
        f"of the product and every edge of the frame. This includes any strap, cord, lace, "
        f"buckle, tag, or other part that dangles or extends outward from the product's main "
        f"body — when framing/cropping, measure the product's full extent by that outermost "
        f"dangling part, not just its main body silhouette, so nothing gets cut off at any "
        f"edge just because it sticks out further than the rest of the product. The "
        f"safe-interior margins in the next paragraph are a hard limit, not a target to fill: "
        f"if in doubt, size the product "
        f"noticeably smaller with more breathing room rather than risk it touching, crowding, "
        f"or extending toward the frame's border.\n\n"
        f"{safe_zone_line}\n\n"
        f"{_product_positioning_instruction()}\n\n"
        f"{_ecommerce_readability_instruction()}\n\n"
        f"Top-left ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of height, "
        f"measured from the very corner): render this rectangle as pure continuation of the "
        f"background itself — same scene, same blur, same exposure as the rest of that "
        f"photo. Do NOT draw any logo, badge, wordmark, text, or shape there — and just as "
        f"importantly, do NOT draw any plain white/light card, plaque, panel, sign, or blank "
        f"rectangle there either, even as a placeholder or empty design element. A real brand "
        f"logo badge graphic gets composited there afterward at those exact pixels.\n\n"
        f"PRODUCT ACCURACY (most important rule)\n"
        f"The product must be pixel-accurate to the FIRST attached reference photo — exact "
        f"real shape, color, material, texture, pattern, logo, and every visible detail — "
        f"including any small attached part (straps, laces, cords, buckles, zippers, "
        f"stitching, hanging tags, or any other accessory) rendered in full. Zero "
        f"redesigning, zero substituting a similar-looking product or a different "
        f"color/material than what's actually shown, and zero blending in any detail from "
        f"the second (style-only) reference image. This card exists specifically to show "
        f"what this ONE variant genuinely looks like, so never invent, adjust, idealize, "
        f"retouch, or \"clean up\" its color/material/shape/condition away from the "
        f"reference, and never drop, shrink, or simplify away any part of it either — every "
        f"detail visible in the reference photo must be visible here too. The product must "
        f"appear "
        f"completely by itself: no person, hand, model, toy, or any other object next to, "
        f"holding, or wearing it — only the product alone. Ultra realistic product "
        f"photography, hyper-detailed high-resolution texture — every stitch, seam, grain, "
        f"and surface detail crisp and clearly visible, never smoothed-over or low-detail — "
        f"razor-sharp, perfectly in-focus, absolutely no blur or softness on it, dramatic "
        f"lighting, natural shadow beneath the product.\n\n"
        f"BACKGROUND\n"
        + (
            f"Use this exact scene, as given by the user, for the background: "
            f"\"{scene_description.strip()}\". "
            if scene_description and scene_description.strip()
            else (
                f"Look at the product itself in the FIRST attached image plus its name "
                f"\"{safe_product}\" and figure out where this specific item actually gets "
                f"used in real life — the scene must be a believable, specific real-world "
                f"environment for THAT product (e.g. a wet construction site or rainy "
                f"outdoor jobsite for rain boots/waterproof gear, a scaffolding or elevated "
                f"structure for fall-protection harnesses, a workshop or factory floor for "
                f"hand tools/PPE, a warehouse for industrial gear), never a generic, "
                f"unrelated, or purely decorative backdrop chosen just because it looks nice. "
            )
        )
        + f"{_background_mood_instruction(framing)} Keep it clean and uncluttered above "
        f"everything else: minimal visual noise, no chaotic jumble of shapes/objects, "
        f"shallow depth of field. Critically, the background's own dominant color/tone must "
        f"stay visibly different from the product's own color in the FIRST attached image — "
        f"never a near-identical hue or brightness that lets the product's silhouette blend "
        f"into the scene behind it. If the believable real-world setting you picked would "
        f"naturally share the product's color (e.g. a similarly-colored surface or wall), "
        f"choose a different camera angle, distance, or a secondary surface/element within "
        f"that same setting so the product still reads as clearly separated from its "
        f"background at a glance. The overall result must read as a premium, professional "
        f"commercial product campaign — polished lighting, believable context, nothing that "
        f"looks staged, cheap, or randomly generated.\n\n"
        f"HEADLINE\n"
        f"Modern premium sans-serif typography, inspired by Helvetica Neue, Gotham, DIN, "
        f"Montserrat ExtraBold. Excellent letter spacing. Clean hierarchy. No outline "
        f"stroke. Soft natural shadow only. Professional kerning.\n\n"
        f"Two lines: the FIRST line is the product's short, generic type name, smaller and "
        f"plain white — a clearly secondary/supporting line, not competing with the variant "
        f"name for attention. Directly below it, the SECOND line is the variant name, colored "
        f"{accent_hex} (matching how the reference image colors its own variant word). Both "
        f"spelled EXACTLY as given below, character for character, no typos, no extra or "
        f"missing letters, each appearing exactly ONCE, no other word added anywhere.\n"
        f"PRODUCT NAME (line 1, smaller, white, verbatim or a brief 2-5 word paraphrase if "
        f"the literal string is long or full of SKU/marketing clutter, exactly once): "
        f"\"{safe_product}\"\n"
        f"VARIANT (line 2, colored {accent_hex}, verbatim, exactly once): \"{safe_name}\"\n\n"
        f"Left-aligned, stacked vertically as two lines, always positioned along the LEFT "
        f"side of the frame — never centered, never on the right side, and never floating "
        f"over the product. This left alignment is fixed and non-negotiable. The vertical "
        f"position, however, is flexible: prefer the upper-left area (below the reserved "
        f"top-left rectangle) like the reference image, but if that spot would sit too "
        f"close to the top frame border to leave comfortable margin, move the headline "
        f"further down the left side instead — a lower placement is always better than "
        f"crowding or risking any overlap with the top of the frame. Size the text to fit "
        f"comfortably for this product photo and text length. The only two rules that "
        f"always apply, no matter the exact size or vertical position: (1) it must "
        f"never touch, cross, or run under the frame border described in the safe-interior "
        f"paragraph above — treat that as the true edge of the canvas; (2) the headline's "
        f"ENTIRE bounding box — both lines, every character, including the leftmost edge of "
        f"the very first letter — must never overlap the reserved top-left rectangle "
        f"described above by even one pixel (that space is for a logo badge composited in "
        f"afterward; a badge is opaque, so any character straddling that boundary gets its "
        f"left half silently erased and its right half left floating, which reads as broken, "
        f"half-missing text — worse than not fitting at all). A headline that starts even "
        f"slightly inside that rectangle and runs out the right side is NOT compliant, even "
        f"if most of it ends up outside — the test is where it STARTS, not where it mostly "
        f"sits. If there is any doubt, do not place the headline anywhere overlapping the "
        f"top {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of the frame's height while also within the "
        f"left {round(_DEAD_ZONE_WIDTH_PCT*100)}% of its width — safe, unambiguous choices "
        f"are starting the headline below that rectangle's bottom edge (lower on the frame), "
        f"or starting it to the right of that rectangle's right edge, whichever reads better "
        f"with this product's shape. Pick whichever size and line-wrapping makes both lines "
        f"fit completely, comfortably, and legibly inside those two limits — a smaller, "
        f"fully-compliant, fully-clear-of-both-zones title is always better than a larger one "
        f"that bleeds into the border or even partially clips the reserved rectangle.\n\n"
        f"COLOR PALETTE\n"
        f"{primary_hex} (corporate accent), {accent_hex} (brand accent, used for the variant "
        f"word in the headline), white, dark dramatic environmental tones.\n\n"
        f"LIGHTING\n"
        f"Cinematic dramatic lighting. Soft rim light. Ambient light. Global illumination. "
        f"Realistic reflections. Photorealistic.\n\n"
        f"QUALITY\n"
        f"Award-winning advertising. Luxury commercial photography. Professional product "
        f"campaign. Ultra realistic. Hyper detailed. 8K. Extremely sharp. No clutter. Minimal. "
        f"Premium. The image must fill the entire square frame edge to edge — no borders, no "
        f"blank margins, nothing cropped off. No watermarks, no UI chrome, no placeholder text "
        f"anywhere other than the exact headline text specified above."
    )

    if extra_instruction.strip():
        prompt += (
            f"\n\nADDITIONAL USER INSTRUCTION (apply on top of everything above, without "
            f"breaking any of the layout/safety rules already specified — and without "
            f"loosening product accuracy: the product must still match the attached "
            f"reference photo exactly in shape/color/material/every detail, regardless of "
            f"what this instruction asks for): \"{extra_instruction.strip()}\""
        )

    try:
        result_bytes = _generate_designed_card_image(prompt, cutout_photo, "varian", framing)
        card = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        if card.size != CARD_SIZE:
            card = _fit_on_blurred_canvas(card, CARD_SIZE)
        _patch_dead_zone(card, theme["primary"], framing)
        card.alpha_composite(_load_framing_image(framing))
        return card
    except Exception:
        logger.exception("AI varian card generation failed for %s (%s)", product_name, variant_name)
        return None


def generate_ai_designed_usage_card(
    cutout_photo: Image.Image, product_name: str, steps: list[dict[str, str]],
    scene_description: str, subtitle: str = "", palette: str = DEFAULT_PALETTE, framing: str = DEFAULT_FRAMING,
    extra_instruction: str = "",
) -> Image.Image | None:
    """The whole "cara penggunaan" card — background, hero product shot, logo
    badge, "CARA PENGGUNAAN" heading, and the numbered step callouts —
    generated as one single AI image, the same idea as
    `generate_ai_designed_keypoint_card` but for the usage card. Each step
    callout is imagined by the model itself from its caption/scene
    description rather than composited from a separately-generated photo,
    so the whole poster reads as one coherent, deliberately designed shot
    instead of a product photo with circles glued on top.

    Same trade-off as the keypoint full-design path: the heading and step
    captions are drawn by the image model itself, not deterministic PIL
    text, so a word can occasionally come out misspelled — callers/users
    should treat the result as a draft to proofread, not a guaranteed-
    correct final asset."""
    theme = _theme_colors(palette, True)
    primary_hex = "#%02x%02x%02x" % theme["primary"]
    accent_hex = "#%02x%02x%02x" % theme["accent"]
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    scene_hint = (
        f" Background environment, deliberately matching this product's own theme/category "
        f"(kept clean, simple, and uncluttered above all else): {scene_description}."
        if scene_description else _default_scene_hint()
    )
    real_steps = [s for s in steps if s.get("caption")][:4]
    safe_zone_line = _frame_safe_zone_instruction(framing)
    style_ref_line = _style_reference_instruction("usage", framing)

    prompt = (
        f"Create a premium commercial \"how to use\" product-instruction poster for a "
        f"{_brand_category_label(framing)} brand.{brand_line}{style_ref_line}\n\n"
        f"STYLE\n"
        f"Modern, premium, clean, corporate branding. Inspired by {_style_benchmark(framing)} "
        f"product advertisements.\n\n"
        f"LAYOUT\n"
        f"Square 1:1 poster, divided top-to-bottom into three bands.\n\n"
        f"{safe_zone_line} This matters most for the FOOTER BAND below, since some brands' "
        f"frame artwork includes a colored tab along the bottom edge — never let a step "
        f"circle or its caption end up partly covered by it.\n\n"
        f"COMPOSITION SAFETY\n"
        f"Keep the complete product silhouette, every step circle, every number badge, and "
        f"all heading/subtitle/caption text fully visible with comfortable negative space. "
        f"Nothing may touch or run beyond the outer edge of the square. Leave at least 6% "
        f"breathing room around the hero product and every text group, in addition to the "
        f"brand-frame safe area above. If the design feels crowded, make the product, "
        f"circles, and typography slightly smaller rather than cropping anything.\n\n"
        f"{_product_positioning_instruction()}\n\n"
        f"{_ecommerce_readability_instruction()}\n\n"
        f"Top-left ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of height, "
        f"measured from the very corner): leave completely empty and plain — soft blurred "
        f"background only, absolutely no logo, badge, wordmark, text, or shape drawn inside "
        f"that exact rectangle. CRITICAL: this also means no duplicate, cropped, or partial "
        f"second copy of the heading/title text (or any other text on this card) may bleed "
        f"into or peek out of this rectangle — every piece of text on the card is drawn "
        f"exactly once, at its own correct position elsewhere, never echoed or restarted "
        f"here. A real brand logo badge graphic gets composited there "
        f"afterward at those exact pixels, so anything drawn there gets covered up or "
        f"clashes with it.\n\n"
        f"TOP BAND (roughly the top 20% of the frame, spanning the full width):\n"
        f"A large bold two-line heading reading exactly \"CARA\" then \"PENGGUNAAN\" on the "
        f"next line, left-aligned. CRITICAL — the reserved top-left rectangle described "
        f"above ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% "
        f"of height, measured from the very top-left corner) belongs ONLY to that empty "
        f"reserved area — this heading's very first line (\"CARA\") must start BELOW the "
        f"bottom edge of that rectangle, never beside it, never overlapping it, never at "
        f"the same height as it even partially. Leave clear vertical breathing room between "
        f"the bottom of the reserved rectangle and the top of \"CARA\" — if unsure, start "
        f"the heading lower rather than risk any overlap. Once clear of that rectangle, "
        f"the heading is left-aligned starting near the left edge. \"CARA\" in white, "
        f"\"PENGGUNAAN\" in {accent_hex}. Modern premium sans-serif typography (Helvetica "
        f"Neue / Gotham / DIN / Montserrat ExtraBold feel), bold, excellent letter spacing, "
        f"soft natural drop shadow only, no outline stroke. This heading "
        f"appears exactly ONCE on the entire card, right here in this band only — never "
        f"a second time, never partially repeated near the top-left corner or anywhere "
        f"else. No other text anywhere in this band — do not repeat the product name. Even "
        f"though the reference image shows a row of small feature icons (e.g. a shield, a "
        f"feather, a badge, each with a short one-word label) directly beneath its own "
        f"heading, do NOT include that icon row here — this band contains ONLY the two-line "
        f"heading and nothing else beneath it; leave that space as plain continuation of "
        f"the background instead.\n\n"
        f"MIDDLE BAND (the middle ~55% of the frame):\n"
        f"The exact product shown in the FIRST attached image (the real product photo) as "
        f"the hero, large scale, "
        f"prominently centered, ultra realistic product photography, shown completely by "
        f"itself with no person, hand, model, toy, or other object next to or holding it in "
        f"this main hero shot. Must match the FIRST attached image (the real product photo) "
        f"exactly — same shape, same colors, same materials/textures, same logo and every "
        f"printed label/text on it, same proportions between its parts — with every single "
        f"part and component fully present, including every small attached part (straps, "
        f"laces, cords, buckles, zippers, stitching, hanging tags, or any other small "
        f"accessory attached to the product) — none of these may be omitted, shortened, "
        f"simplified, merged together, or redesigned even slightly just because they're "
        f"small. Natural realistic shadow, soft "
        f"reflection on a wet/glossy floor if applicable, cinematic lighting, hyper-detailed "
        f"high-resolution texture — every stitch, seam, grain, and surface detail crisp and "
        f"clearly visible, never smoothed-over or low-detail — razor-sharp, perfectly "
        f"in-focus product, absolutely no blur or softness on it, with the background in a "
        f"gentle shallow depth of field.{scene_hint} The product must stay fully inside this middle "
        f"band, never extending up into the heading band or down into the footer band below. "
        f"The lowest edge of the product must sit above 64% of the poster height; the footer "
        f"band starts below that and must not cover the product.\n\n"
        f"FOOTER BAND (the bottom ~25% of the frame, spanning the full width):\n"
        f"The same continuous background scene from the middle band carries on through here "
        f"— no solid color panel, gradient block, or any other shape painted behind this "
        f"band; it must read as one uninterrupted photo top to bottom, not a photo with a "
        f"colored box stuck on at the bottom. Exactly {len(real_steps)} evenly-spaced "
        f"circular photo callouts arranged in a single horizontal row — and NOTHING else in "
        f"this band beyond those {len(real_steps)} circles, their ring borders, their number "
        f"badges, and their title/description text; do not add any extra circle, icon, badge, "
        f"line, shape, or decorative element to fill leftover space between or around them, "
        f"even if the row looks like it has empty gaps — plain uninterrupted background fills "
        f"any leftover space instead. Every one of these {len(real_steps)} circles, its ring, "
        f"and its number badge must sit entirely within the safe interior area from the "
        f"safe-zone instructions above with clear margin from the bottom/side edges — this is "
        f"the single most common place a circle ends up half-hidden under the brand's bottom "
        f"tab, so keep the whole row noticeably higher/smaller rather than risk that. Each "
        f"circle has a thin accent-color ring border and a small numbered accent-color badge "
        f"on its lower-right edge, matching the reference image's own badge style/position "
        f"exactly. Each circle shows a photorealistic close-up of a person's hands "
        f"or feet actually performing that specific step with this exact product (preserve "
        f"the product's real appearance in every circle) — not the same repeated shot, a "
        f"different moment per step. Beneath each circle: only a short bold white title line, "
        f"with a soft natural drop shadow for contrast (no colored panel or box behind the "
        f"text itself) — no second line, no smaller description text underneath it.\n\n"
        f"Step-by-step, left to right — each circle's photo content and the title "
        f"beneath it must always be this exact matching set, never mixed up with another "
        f"step's:\n"
        + "\n".join(
            f"Step {i + 1}: photo = {s.get('scene') or s['caption']}; "
            f"bold title beneath it (its only line of text), spelled exactly = \"{s['caption']}\""
            for i, s in enumerate(real_steps)
        ) + "\n\n"
        f"COLOR PALETTE\n"
        f"{primary_hex} (corporate blue), {accent_hex} (brand accent), white, dark gray.\n\n"
        f"LIGHTING\n"
        f"Cinematic lighting. Soft rim light. Ambient light. Global illumination. Realistic "
        f"reflections. Photorealistic.\n\n"
        f"QUALITY\n"
        f"Award-winning advertising. Luxury commercial photography. Professional product "
        f"campaign. Ultra realistic. Hyper detailed. 8K. Extremely sharp. No clutter. "
        f"Minimal. Premium. The image must fill the entire square frame edge to edge — no "
        f"borders, no blank margins, nothing cropped off. No watermarks, no UI chrome, no "
        f"placeholder text anywhere other than the exact strings specified above."
    )

    if extra_instruction.strip():
        prompt += (
            f"\n\nADDITIONAL USER INSTRUCTION (apply on top of everything above, without "
            f"breaking any of the layout/safety rules already specified — and without "
            f"loosening product accuracy: the product must still match the attached "
            f"reference photo exactly in shape/color/material/every detail, regardless of "
            f"what this instruction asks for): \"{extra_instruction.strip()}\""
        )

    try:
        result_bytes = _generate_designed_card_image(prompt, cutout_photo, "usage", framing)
        card = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        if card.size != CARD_SIZE:
            card = _fit_on_blurred_canvas(card, CARD_SIZE)
        _patch_dead_zone(card, theme["primary"], framing)
        card.alpha_composite(_load_framing_image(framing))
        return card
    except Exception:
        logger.exception("AI full-design usage card generation failed for %s", product_name)
        return None


def generate_ai_designed_spec_card(
    cutout_photo: Image.Image, product_name: str, spec: dict[str, str], keypoints: list[str],
    scene_description: str, manual_lines: list[str] | None = None,
    palette: str = DEFAULT_PALETTE, framing: str = DEFAULT_FRAMING,
    extra_instruction: str = "",
) -> Image.Image | None:
    """The whole "spesifikasi produk" card — background, hero product shot,
    logo badge, title/tagline, the spec field rows (each with its own small
    icon), and a bottom highlight bar — generated as one single AI image,
    the same idea as `generate_ai_designed_keypoint_card`/
    `generate_ai_designed_usage_card` but for the spec card.

    Same trade-off as the other full-design paths: the headline, tagline,
    and every spec row are drawn by the image model itself, not
    deterministic PIL text, so a word can occasionally come out misspelled
    — callers/users should treat the result as a draft to proofread, not a
    guaranteed-correct final asset."""
    theme = _theme_colors(palette, True)
    primary_hex = "#%02x%02x%02x" % theme["primary"]
    accent_hex = "#%02x%02x%02x" % theme["accent"]
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    scene_hint = (
        f" Background environment, deliberately matching this product's own theme/category "
        f"(kept clean, simple, and uncluttered above all else): {scene_description}."
        if scene_description else _default_scene_hint()
    )
    safe_zone_line = _frame_safe_zone_instruction(framing)
    tagline = (spec.get("tagline") or "").strip()
    tagline_line = f" Tagline directly beneath it, spelled exactly = \"{tagline}\"." if tagline else ""
    deskripsi = (spec.get("deskripsi") or "").strip()
    deskripsi_line = (
        f" Below the tagline, a short 2-3 line description paragraph in a smaller, lighter-"
        f"weight regular font, spelled exactly = \"{deskripsi}\"."
        if deskripsi else ""
    )

    if manual_lines:
        # User typed the spec rows by hand — render exactly those, one row
        # each, no "LABEL: value" pairing or icon-matching guesswork.
        row_instructions = "\n".join(f"Row {i + 1}: spelled exactly = \"{line}\"" for i, line in enumerate(manual_lines))
        real_fields = manual_lines
    else:
        field_labels = [
            ("ITEM NAME", spec.get("item_name", "-")),
            ("UKURAN", spec.get("ukuran", "-")),
            ("MATERIAL", spec.get("material", "-")),
            ("RING & BUCKLE", spec.get("ring_buckle", "-")),
            ("KAPASITAS", spec.get("kapasitas", "-")),
            ("APLIKASI", spec.get("aplikasi", "-")),
        ]
        real_fields = [(label, value) for label, value in field_labels if value and value.strip() not in ("", "-")]
        row_instructions = "\n".join(
            f"Row {i + 1}: icon = the clearest possible symbol for \"{label}\"; label = \"{label}\"; "
            f"value beside it on the same row, spelled exactly = \"{value}\""
            for i, (label, value) in enumerate(real_fields)
        )

    real_keypoints = [kp for kp in keypoints if kp][:4]
    style_ref_line = _style_reference_instruction("spec", framing)

    prompt = (
        f"Create a premium commercial product specification sheet for a "
        f"{_brand_category_label(framing)} brand.{brand_line}{style_ref_line}\n\n"
        f"STYLE\n"
        f"Modern, premium, clean, corporate branding. Inspired by {_style_benchmark(framing)} "
        f"product spec sheets.\n\n"
        f"LAYOUT\n"
        f"Square 1:1 poster.\n\n"
        f"{safe_zone_line}\n\n"
        f"COMPOSITION SAFETY\n"
        f"Keep the complete product silhouette, the logo badge area, and every spec row/icon "
        f"fully visible with comfortable negative space. Nothing may touch, cross, or run "
        f"beyond the outer edge of the square, and the product must never overlap or crowd "
        f"the spec rows on the right side. Leave at least 6% clear breathing room around the "
        f"hero product and all text groups, in addition to the brand-frame safe area above. "
        f"If the layout feels crowded, make the product and typography slightly smaller "
        f"rather than pushing anything off canvas or letting it run under the frame.\n\n"
        f"{_product_positioning_instruction()}\n\n"
        f"{_ecommerce_readability_instruction()}\n\n"
        f"Top-left ({round(_DEAD_ZONE_WIDTH_PCT*100)}% of width x {round(_DEAD_ZONE_HEIGHT_PCT*100)}% of height, "
        f"measured from the very corner): leave completely empty and plain — soft blurred "
        f"background only, absolutely no logo, badge, wordmark, text, or shape drawn inside "
        f"that exact rectangle. CRITICAL: this also means no duplicate, cropped, or partial "
        f"second copy of the heading/title text (or any other text on this card) may bleed "
        f"into or peek out of this rectangle — every piece of text on the card is drawn "
        f"exactly once, at its own correct position elsewhere, never echoed or restarted "
        f"here. A real brand logo badge graphic gets composited there "
        f"afterward at those exact pixels, so anything drawn there gets covered up or "
        f"clashes with it.\n\n"
        f"LEFT SIDE:\n"
        f"The exact product shown in the FIRST attached image (the real product photo) as "
        f"the hero, framed the "
        f"way a real marketplace/e-commerce listing photo (Shopee, Tokopedia, Amazon) frames "
        f"its main product shot: large, dominant, and unmistakably the focal point, filling "
        f"roughly half to two-thirds of this side's height, never small, distant, or lost in "
        f"the scene. POSITIONING is critical — pick whichever natural resting position best "
        f"shows off the whole product the way a good marketplace listing photo would (e.g. "
        f"standing upright on a surface, neatly laid flat, or hung straight from its own "
        f"strap/hook), fully upright and level, not tilted, floating at a random angle, "
        f"twisted, folded oddly, or awkwardly cropped by the frame edge — the complete "
        f"product must be visible with clean margin on all sides, in the same orientation "
        f"and pose customers would expect from a real product listing, never a strange or "
        f"unnatural pose even if the reference photo itself was cropped or awkwardly angled. "
        f"Every real detail — shape, texture, color, logo, printed text on the product — must "
        f"stay sharp, crisp, and clearly legible even at a glance, exactly as it is in the "
        f"FIRST attached image (the real product photo), with every part and component fully "
        f"present, including every small attached part (straps, laces, cords, buckles, "
        f"zippers, stitching, hanging tags, or any other small accessory attached to the "
        f"product) — none of these may be omitted, shortened, simplified, or merged together "
        f"just because they're small — do not redesign, restyle, recolor, or leave out any "
        f"part of the product itself. The product must "
        f"appear completely by itself: no person, hand, model, toy, or any other object next "
        f"to, holding, or wearing it — only the product alone. Ultra realistic product "
        f"photography, natural realistic shadow, "
        f"cinematic lighting, hyper-detailed high-resolution texture — every stitch, seam, "
        f"grain, and surface detail crisp and clearly visible, never smoothed-over or "
        f"low-detail — razor-sharp, perfectly in-focus product, absolutely no blur or "
        f"softness on it, with the background in a gentle shallow depth of field so it stays "
        f"clearly secondary and never competes with the product.{scene_hint}\n\n"
        f"RIGHT SIDE (top to bottom):\n"
        f"1. Product title, spelled EXACTLY as given, no word or line repeated/duplicated "
        f"anywhere — appears exactly ONCE on the card: \"{product_name}\" — large bold "
        f"headline, up to 2 lines, modern "
        f"premium sans-serif (Helvetica Neue / Gotham / DIN / Montserrat ExtraBold feel), "
        f"excellent letter spacing, soft natural drop shadow only, no outline stroke, "
        f"styled with a subtle textured/weathered look on the first line and solid "
        f"{accent_hex} on the rest — same premium two-tone title treatment as the reference "
        f"image.{tagline_line}{deskripsi_line}\n"
        f"2. A bordered spec table directly below the description — a thin rounded rectangle "
        f"outline in {accent_hex} containing the header \"SPESIFIKASI PRODUK\" at its top, "
        f"then a vertical stack of spec rows separated by thin faint divider lines, each row "
        f"on a single line: a small outline icon on the far left, the label in {accent_hex} "
        f"next to it, a colon \":\" as a separator, then the value in white filling the rest "
        f"of that same row — evenly spaced, comfortable breathing room, never crowding the "
        f"row above or below it. Icons: minimal thin outline/stroke style (Feather Icons / "
        f"Material Symbols outlined feel), consistent icon family across all rows, white "
        f"icon.\n\n"
        f"Spec rows, top to bottom — EXACTLY {len(real_fields)} rows, each icon/label/value "
        f"is this exact matching set, never mixed up with another row's, and no row or label "
        f"ever repeated/duplicated — each of these appears exactly ONCE, in this exact order, "
        f"nowhere else on the card:\n{row_instructions}\n\n"
        + (
            f"FOOTER BAND (the bottom ~12% of the frame, spanning the full width):\n"
            f"A solid or gradient dark panel containing exactly {len(real_keypoints)} evenly-"
            f"spaced cells arranged in a single horizontal row, each with a small white "
            f"outline icon beside (not above) a short bold white title, one cell per "
            f"highlight below, spelled exactly, never mixed up with another cell's:\n"
            + "\n".join(f"Cell {i + 1}: icon = the clearest symbol for \"{kp}\"; title = \"{kp}\"" for i, kp in enumerate(real_keypoints))
            + "\n\n"
            if real_keypoints else ""
        )
        + f"COLOR PALETTE\n"
        f"{primary_hex} (corporate blue), {accent_hex} (brand accent), white, dark gray.\n\n"
        f"LIGHTING\n"
        f"Cinematic lighting. Soft rim light. Ambient light. Global illumination. Realistic "
        f"reflections. Photorealistic.\n\n"
        f"QUALITY\n"
        f"Award-winning advertising. Luxury commercial photography. Professional product "
        f"campaign. Ultra realistic. Hyper detailed. 8K. Extremely sharp. No clutter. "
        f"Minimal. Premium. The image must fill the entire square frame edge to edge — no "
        f"borders, no blank margins, nothing cropped off. No watermarks, no UI chrome, no "
        f"placeholder text anywhere other than the exact strings specified above."
    )

    if extra_instruction.strip():
        prompt += (
            f"\n\nADDITIONAL USER INSTRUCTION (apply on top of everything above, without "
            f"breaking any of the layout/safety rules already specified — and without "
            f"loosening product accuracy: the product must still match the attached "
            f"reference photo exactly in shape/color/material/every detail, regardless of "
            f"what this instruction asks for): \"{extra_instruction.strip()}\""
        )

    try:
        result_bytes = _generate_designed_card_image(prompt, cutout_photo, "spec", framing)
        card = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        if card.size != CARD_SIZE:
            card = _cover_crop(card, CARD_SIZE)
        _patch_dead_zone(card, theme["primary"], framing)
        card.alpha_composite(_load_framing_image(framing))
        return card
    except Exception:
        logger.exception("AI full-design spec card generation failed for %s", product_name)
        return None


def _icon_droplet(card: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, primary: tuple[int, int, int] = NAVY) -> None:
    draw.pieslice([cx - r, cy - r * 0.2, cx + r, cy + r * 1.4], 0, 360, fill=WHITE)
    draw.polygon(
        [(cx - r * 0.7, cy), (cx + r * 0.7, cy), (cx, cy - r * 1.3)], fill=WHITE
    )


def _icon_bolt(card: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, primary: tuple[int, int, int] = NAVY) -> None:
    pts = [
        (cx + r * 0.15, cy - r), (cx - r * 0.65, cy + r * 0.15), (cx, cy + r * 0.15),
        (cx - r * 0.15, cy + r), (cx + r * 0.65, cy - r * 0.15), (cx, cy - r * 0.15),
    ]
    draw.polygon(pts, fill=WHITE)


def _icon_tag(
    card: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float,
    primary: tuple[int, int, int] = NAVY,
) -> None:
    draw.polygon(
        [
            (cx - r * 0.9, cy - r * 0.2), (cx + r * 0.3, cy - r * 0.9),
            (cx + r * 0.9, cy - r * 0.3), (cx - r * 0.1, cy + r * 0.9),
        ],
        fill=WHITE,
    )
    draw.ellipse(
        [cx + r * 0.1, cy - r * 0.6, cx + r * 0.35, cy - r * 0.35], fill=primary
    )


def _icon_check(card: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, primary: tuple[int, int, int] = NAVY) -> None:
    draw.line(
        [(cx - r * 0.6, cy), (cx - r * 0.15, cy + r * 0.5), (cx + r * 0.65, cy - r * 0.55)],
        fill=WHITE, width=max(3, int(r * 0.22)), joint="curve",
    )


def _draw_glossy_badge(
    card: Image.Image, cx: float, cy: float, radius: float,
    base_color: tuple[int, int, int], ring_color: tuple[int, int, int],
) -> None:
    """A flat solid-fill circle reads as cheap/programmatic next to a real
    designer's glassmorphism-style badge (soft radial gradient, gentle drop
    shadow, subtle glossy highlight) — this draws that same effect with
    plain PIL compositing, layer by layer, so the badge looks hand-designed
    even though the position/size/color are still fully deterministic (no
    AI risk to the product name/text anywhere on the card)."""
    pad = max(40, round(radius * 0.85))
    size = round((radius + pad) * 2)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    center = size / 2

    # Soft colored outer glow, bled well past the circle's own edge — the
    # reference badges read as backlit/glowing, not just glossy; without
    # this they come across as flat "no cahaya" next to that reference no
    # matter how much shine the gradient/highlight below add on their own.
    # Uses _vivid_glow (boosts brightness while flooring saturation) rather
    # than _lighten (blends toward white) — _lighten desaturates as it
    # brightens, so a navy badge's glow read as a flat pale-white halo next
    # to the reference's electric, clearly-still-blue rim light. Drawn in
    # two blurred passes — a wider/dimmer outer bloom plus a tighter/
    # brighter inner one — for a real glow falloff instead of one flat
    # blurred blob.
    glow_color = _vivid_glow(base_color, value=1.0, min_saturation=0.6)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        [center - radius * 1.35, center - radius * 1.35, center + radius * 1.35, center + radius * 1.35],
        fill=glow_color + (140,),
    )
    glow_draw.ellipse(
        [center - radius * 1.05, center - radius * 1.05, center + radius * 1.05, center + radius * 1.05],
        fill=glow_color + (200,),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius * 0.32))
    layer.alpha_composite(glow)

    # Extra rim-light arc hugging the top edge of the circle — the
    # reference's glow isn't an even halo all the way around, it's brightest
    # right at the top rim (as if lit from above) and fades toward the
    # bottom. The two symmetric ellipse passes above give the ambient bloom;
    # this adds the concentrated bright arc on top of that.
    rim = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rim_draw = ImageDraw.Draw(rim)
    rim_draw.arc(
        [center - radius - 3, center - radius - 3, center + radius + 3, center + radius + 3],
        start=200, end=340, fill=glow_color + (255,), width=max(4, round(radius * 0.12)),
    )
    rim = rim.filter(ImageFilter.GaussianBlur(radius * 0.06))
    layer.alpha_composite(rim)

    # Soft drop shadow, offset down/right and blurred, instead of a hard
    # edge — gives the badge real depth against the card behind it.
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        [center - radius, center - radius + radius * 0.12, center + radius, center + radius + radius * 0.12],
        fill=(0, 0, 0, 110),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius * 0.18))
    layer.alpha_composite(shadow)

    # Radial gradient fill (lighter toward the upper-left "light source",
    # deepening toward the base badge color at the opposite edge) instead
    # of one flat color — this alone is most of what reads as "glossy"
    # rather than "flat programmer circle".
    grad_size = round(radius * 2) + 2
    yy, xx = np.mgrid[0:grad_size, 0:grad_size]
    gcx, gcy = grad_size * 0.36, grad_size * 0.32
    dist = np.sqrt((xx - gcx) ** 2 + (yy - gcy) ** 2)
    # A tight falloff (small bright patch near the light source, quickly
    # settling into the true badge color) reads as a glossy sheen on a
    # deep navy sphere; spreading the light tone across the whole circle
    # instead washed the badge out into a flat grayish-blue.
    t = np.clip(dist / (grad_size * 0.55), 0.0, 1.0)
    light = np.array(_lighten(base_color, 0.22), dtype=np.float32)
    dark = np.array(base_color, dtype=np.float32)
    grad_rgb = (light[None, None, :] * (1 - t[..., None]) + dark[None, None, :] * t[..., None]).astype(np.uint8)
    circle_mask = (xx - grad_size / 2) ** 2 + (yy - grad_size / 2) ** 2 <= (grad_size / 2 - 1) ** 2
    grad_rgba = np.dstack([grad_rgb, (circle_mask * 255).astype(np.uint8)])
    gradient_img = Image.fromarray(grad_rgba, "RGBA")
    layer.alpha_composite(gradient_img, (round(center - grad_size / 2), round(center - grad_size / 2)))

    # Ring stroke uses the same vivid hue as the glow (a saturated blue rim,
    # not a flat white circle outline) so the badge edge reads as part of
    # the same glowing light instead of a plain drawn border on top of it.
    # A prior version blended this 75/25 with ring_color (theme["ink"], i.e.
    # white) "to stay on-brand for custom palettes" — but that 25% white
    # was enough to wash the whole ring back out toward white on screen,
    # which is exactly the flat-white-ring look this was meant to fix. Pure
    # vivid hue reads correctly as blue and still tracks each palette's own
    # badge color since it's derived from base_color, not a hardcoded blue.
    ring_stroke = _vivid_glow(base_color, value=0.95, min_saturation=0.75)
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        [center - radius, center - radius, center + radius, center + radius],
        outline=ring_stroke, width=4,
    )

    # Glossy highlight: a soft, blurred white crescent across the upper
    # portion of the circle, like light reflecting off a curved glass
    # surface — clipped to the circle so it never spills past the edge.
    highlight = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).ellipse(
        [center - radius * 0.72, center - radius * 0.85, center + radius * 0.55, center - radius * 0.05],
        fill=(255, 255, 255, 95),
    )
    highlight = highlight.filter(ImageFilter.GaussianBlur(radius * 0.14))
    clip_mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(clip_mask).ellipse(
        [center - radius, center - radius, center + radius, center + radius], fill=255,
    )
    highlight.putalpha(ImageChops.multiply(highlight.getchannel("A"), clip_mask))
    layer.alpha_composite(highlight)

    card.alpha_composite(layer, (round(cx - center), round(cy - center)))


def _composite_icon_image(card: Image.Image, icon: Image.Image, cx: float, cy: float, r: float) -> None:
    # 3.1x here (not the vector icons' ~1.9x r) because these are the real
    # cropped/generated glyph images, which are proportioned close to their
    # native pixel size already — the old 1.9x factor shrank them to ~40% of
    # the badge instead of the reference's actual ~60-65% fill.
    scale = (r * 3.1) / max(icon.width, icon.height)
    new_size = (max(1, round(icon.width * scale)), max(1, round(icon.height * scale)))
    resized = icon.resize(new_size, Image.LANCZOS)
    paste_x = round(cx - new_size[0] / 2)
    paste_y = round(cy - new_size[1] / 2)
    card.alpha_composite(resized, (paste_x, paste_y))


def _icon_asset(name: str):
    """Build an icon-drawing callback that pastes a real cropped icon image
    (from assets/icons/) instead of drawing a vector approximation."""

    def _draw(card: Image.Image, draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, primary: tuple[int, int, int] = NAVY) -> None:
        _composite_icon_image(card, _load_icon_image(name), cx, cy, r)

    return _draw


_ICON_KEYWORDS: list[tuple[tuple[str, ...], object]] = [
    (("air", "water", "tahan air", "waterproof", "anti air"), _icon_droplet),
    (("aman", "safety", "protect", "proteksi", "perlindungan", "fall"), _icon_asset("shield")),
    (("kuat", "strong", "tahan", "durable", "awet", "kokoh", "hook", "carabiner", "pengait", "kaitan"), _icon_asset("link")),
    (("kunci", "lock", "secure", "koneksi", "connection"), _icon_asset("anchor")),
    (("visibility", "terlihat", "visible", "mencolok", "jelas"), _icon_asset("eye")),
    (("reflektif", "reflective", "pantul", "memantul"), _icon_asset("tape")),
    (("ringan", "lightweight", "nyaman", "compact"), _icon_asset("vest")),
    (("harga", "murah", "affordable", "terjangkau", "hemat", "ekonomis"), _icon_tag),
]


def _pick_icon(keyword: str):
    lowered = keyword.lower()
    for keys, icon_fn in _ICON_KEYWORDS:
        if any(k in lowered for k in keys):
            return icon_fn
    return _icon_check


def _wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int,
    letter_spacing: float = 0,
) -> list[str]:
    def width(s: str) -> float:
        return _tracked_width(draw, s, font, letter_spacing) if letter_spacing else draw.textlength(s, font=font)

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if width(candidate) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_title_font(
    draw: ImageDraw.ImageDraw, text: str, max_width: int, max_lines: int = 3,
    start_size: int = 84, min_size: int = 18, step: int = 2, font_theme: str = _DEFAULT_FONT_THEME,
    weight: str = "bold", letter_spacing: float = 0,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Shrink the font until the text still wraps to max_lines, instead of
    pushing extra lines down into — and shrinking — whatever's laid out
    below it. Keeps the layout consistent regardless of how long the text
    is. Never drops words, though: if even min_size still needs more than
    max_lines, the full (untruncated) wrap is returned instead of silently
    cutting off the end of the text — downstream layout (photo/badge
    position) is computed from the actual line count, so extra lines just
    push the rest of the card down instead of losing text."""
    size = start_size
    while size > min_size:
        font = _font(weight, size, font_theme)
        lines = _wrap_text(draw, text, font, max_width, letter_spacing)
        if len(lines) <= max_lines:
            return font, lines
        size -= step
    font = _font(weight, min_size, font_theme)
    return font, _wrap_text(draw, text, font, max_width, letter_spacing)


def _pos_pct(x: float, y: float) -> str:
    w, h = CARD_SIZE
    return f"roughly {round(x / w * 100)}% across and {round(y / h * 100)}% down the image"


def _ai_add_typography(card: Image.Image, instructions: str, framing: str = DEFAULT_FRAMING) -> Image.Image:
    """Hand the card's text off to the AI as a finishing pass instead of
    drawing it with a fixed local font file — the AI picks the typeface,
    weight, and exact styling itself, freely, based on the brand mood.

    The card passed in already has the brand's decorative frame/logo badge
    pasted onto it (see callers) — not just described in words — so the AI
    can literally see its real shape/position and work around it, instead of
    trying to obey a numeric pixel margin blind. The frame is re-pasted on
    top again after this call as a safety net in case the edit altered it.

    Only the text described in `instructions` is added; everything already
    in the image (photo, badges, diagram, frame, colors, layout) must stay
    untouched. Best-effort: on failure, the card is returned exactly as it
    was (still a usable card, just without the added text) instead of
    failing the whole generation."""
    hint = brand_style_hint(framing)
    brand_line = f" {hint}" if hint else ""
    prompt = (
        "Add clean, professional graphic-design typography directly onto this exact "
        "image, finishing it into a polished product marketing card. This image already "
        "has a decorative brand frame/border and logo badge visible on it (you can see "
        "exactly where — usually along the top and around the edges) — treat that as "
        "fixed, already-final artwork: do NOT cover it, overlap it, place any text on "
        "top of it, redraw it, move it, or recolor it in any way. Also do not alter, "
        "redraw, move, or recolor anything else already in the image (the photo, icons, "
        "badges, diagram, colors, layout, or any small text labels already printed "
        "beneath the icon circles) — only add the text described below, on top "
        "of the plain open areas of the image, working around the visible frame/badge. "
        "You choose the font/typeface, weight, size, and exact styling entirely "
        f"yourself — there is no fixed font, pick whatever best fits this card and "
        f"brand.{brand_line}\n\n"
        f"Text to add:\n{instructions}\n\n"
        "Render every piece of text exactly as given, character for character — no "
        "typos, no invented or altered words, no extra text beyond what's listed here. "
        "Legibility is mandatory, not optional: for every single piece of text, first "
        "check what's actually behind it (photo, background scene, or plain color) and "
        "give it real contrast — a solid or soft-edged color panel/pill behind the text, "
        "a strong drop shadow, or a bold outline/stroke on the letters themselves, "
        "whichever fits the design best. Never place raw text directly over a busy, "
        "textured, or similarly-colored area with no separation — if in doubt, add a "
        "dark semi-transparent panel behind light text (or a light one behind dark "
        "text). Every word must be immediately, easily readable at a glance, without "
        "hiding the product photo or the frame/badge. Output the same square image at "
        "the same size, now with this text included."
    )
    try:
        result_bytes = edit_image(prompt, card.convert("RGB"))
        result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
        return result.resize(CARD_SIZE) if result.size != CARD_SIZE else result
    except Exception:
        logger.exception("AI typography pass failed, returning card without its text layer")
        return card


def _paste_fitted_photo(card: Image.Image, photo: Image.Image, box: tuple[int, int, int, int]) -> None:
    """Center the photo/cutout inside `box`, scaled to fill it — a plain,
    direct paste with no drop shadow and no white card/frame behind it.
    Those used to get added automatically (a soft shadow for a real
    transparent cutout, a whole white rounded-rectangle frame + shadow for
    a non-cutout photo), but on a real product shot both read as a stray
    box/line artifact sitting on top of an otherwise clean, professional
    card — the photo alone, unframed, is the correct look here."""
    box_left, box_top, box_right, box_bottom = box
    box_w, box_h = box_right - box_left, box_bottom - box_top

    photo = photo.convert("RGBA")
    # A pure contain-fit (scale so BOTH dimensions stay inside the box) always
    # shrinks to whichever dimension is the tighter fit — for a product whose
    # aspect ratio is very different from the box (e.g. a wide, flat pair of
    # glasses inside a tall box), that leaves a lot of dead space and the
    # product reads as small/lost instead of a comfortable "pas" size. Scale
    # up a further 15% past strict contain-fit so it fills the box properly;
    # a slight, controlled overflow past the box edges looks better than a
    # product floating tiny in the middle of empty space.
    inner_w = max(1, round(box_w * 0.92))
    inner_h = max(1, round(box_h * 0.92))
    scale = min(inner_w / photo.width, inner_h / photo.height)
    new_size = (max(1, int(photo.width * scale)), max(1, int(photo.height * scale)))
    resized = photo.resize(new_size, Image.LANCZOS)

    paste_x = box_left + (box_w - new_size[0]) // 2
    paste_y = box_top + (box_h - new_size[1]) // 2
    card.alpha_composite(resized, (paste_x, paste_y))


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize+crop an image to fully cover `size`, like CSS background-size: cover."""
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(new_size, Image.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def _fit_on_blurred_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize an image into a fixed canvas without cutting off its edges."""
    target_w, target_h = size
    image = image.convert("RGBA")
    background = _cover_crop(image, size).filter(ImageFilter.GaussianBlur(18))
    overlay = Image.new("RGBA", size, (255, 255, 255, 36))
    background.alpha_composite(overlay)

    scale = min(target_w / image.width, target_h / image.height)
    new_size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    fitted = image.resize(new_size, Image.LANCZOS)
    x = (target_w - fitted.width) // 2
    y = (target_h - fitted.height) // 2
    background.alpha_composite(fitted, (x, y))
    return background


def _brand_gradient_background(theme: dict[str, tuple[int, int, int]]) -> Image.Image:
    """Plain brand-color gradient (top-left lighter -> bottom-right darker,
    for depth) used as the card background whenever no AI-generated scene is
    available or applicable. Uses the resolved theme's gradient stops so the
    Gelap/Terang toggle and color palette both actually show up even when
    there's no AI background photo to fall back on."""
    w, h = CARD_SIZE
    card = Image.new("RGBA", CARD_SIZE, theme["gradient_far"])
    gradient = Image.new("L", (w, h))
    gradient_draw = ImageDraw.Draw(gradient)
    for y in range(h):
        intensity = int(255 * (y / h) * 0.35)
        gradient_draw.line([(0, y), (w, y)], fill=intensity)
    tint = Image.new("RGBA", (w, h), theme["gradient_near"] + (255,))
    return Image.composite(tint, card, gradient)


def _draw_centered_shadowed_text(
    card: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    center_x: float,
    top_y: float,
    line_height: float,
    fill: tuple[int, int, int],
) -> None:
    """Draw `lines`, each horizontally centered on `center_x`, stacked
    downward from `top_y`, with a soft dark drop shadow behind them for
    legibility over a photo background. Drawn deterministically with PIL
    (not the AI typography pass) so the position is always exactly where
    the layout math put it — never drifting up, down, or off-center."""
    shadow_layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    text_draw = ImageDraw.Draw(card)
    for i, line in enumerate(lines):
        line_width = text_draw.textlength(line, font=font)
        x = center_x - line_width / 2
        y = top_y + i * line_height
        shadow_draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 190))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(2))
    card.alpha_composite(shadow_layer)
    text_draw = ImageDraw.Draw(card)
    for i, line in enumerate(lines):
        line_width = text_draw.textlength(line, font=font)
        x = center_x - line_width / 2
        y = top_y + i * line_height
        text_draw.text((x, y), line, font=font, fill=fill)


def _tracked_width(draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, letter_spacing: float) -> float:
    return draw.textlength(line, font=font) + letter_spacing * max(0, len(line) - 1)


def _draw_tracked_text(
    draw: ImageDraw.ImageDraw, line: str, font: ImageFont.FreeTypeFont, x: float, y: float,
    fill_or_alpha, letter_spacing: float,
) -> None:
    """draw.text with extra letter-spacing — a bold all-caps geometric sans
    set with its default (near-zero) tracking reads cramped/stiff at large
    display sizes; real display typography always opens the tracking up a
    little at heavy weights/big sizes. No-op loop over single characters
    when letter_spacing is 0, so this is safe to always call."""
    if letter_spacing <= 0:
        draw.text((x, y), line, font=font, fill=fill_or_alpha)
        return
    cursor = x
    for ch in line:
        draw.text((cursor, y), ch, font=font, fill=fill_or_alpha)
        cursor += draw.textlength(ch, font=font) + letter_spacing


def _draw_right_aligned_shadowed_text(
    card: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    right_x: float,
    top_y: float,
    line_height: float,
    fill: tuple[int, int, int],
    letter_spacing: float = 0,
) -> None:
    """Same idea as `_draw_centered_shadowed_text` but right-aligned (each
    line's right edge lands on `right_x`) — used for the title/tagline
    header block, drawn deterministically so its color and position are
    always exactly what the layout math and brand palette say, never left
    to an AI guess."""
    shadow_layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    text_draw = ImageDraw.Draw(card)
    for i, line in enumerate(lines):
        line_width = _tracked_width(text_draw, line, font, letter_spacing)
        x = right_x - line_width
        y = top_y + i * line_height
        _draw_tracked_text(shadow_draw, line, font, x + 2, y + 2, (0, 0, 0, 190), letter_spacing)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(2))
    card.alpha_composite(shadow_layer)
    text_draw = ImageDraw.Draw(card)
    for i, line in enumerate(lines):
        line_width = _tracked_width(text_draw, line, font, letter_spacing)
        x = right_x - line_width
        y = top_y + i * line_height
        _draw_tracked_text(text_draw, line, font, x, y, fill, letter_spacing)


def _draw_left_aligned_shadowed_text(
    card: Image.Image,
    lines: list[str],
    fills: list[tuple[int, int, int]] | tuple[int, int, int],
    font: ImageFont.FreeTypeFont,
    left_x: float,
    top_y: float,
    line_height: float,
    letter_spacing: float = 0,
) -> None:
    """Same idea as `_draw_right_aligned_shadowed_text` but left-aligned (each
    line's left edge lands on `left_x`), with an optional different fill
    color per line (e.g. a two-tone heading like the reference brand cards)."""
    fill_list = fills if isinstance(fills, list) else [fills] * len(lines)
    shadow_layer = Image.new("RGBA", card.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow_layer)
    for i, line in enumerate(lines):
        y = top_y + i * line_height
        _draw_tracked_text(shadow_draw, line, font, left_x + 2, y + 2, (0, 0, 0, 190), letter_spacing)
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(2))
    card.alpha_composite(shadow_layer)
    text_draw = ImageDraw.Draw(card)
    for i, line in enumerate(lines):
        y = top_y + i * line_height
        _draw_tracked_text(text_draw, line, font, left_x, y, fill_list[i], letter_spacing)


def compose_keypoint_card(
    product_name: str,
    tagline: str,
    keypoints: list[str],
    photo: Image.Image,
    background_photo: Image.Image | None = None,
    keypoint_icons: list[Image.Image | None] | None = None,
    full_scene_photo: Image.Image | None = None,
    font_theme: str = _DEFAULT_FONT_THEME,
    palette: str = DEFAULT_PALETTE,
    dark_theme: bool = True,
    custom_primary: str | None = None,
    custom_accent: str | None = None,
    framing: str = DEFAULT_FRAMING,
) -> bytes:
    """Render the fixed brand template (logo badge, title/tagline, product photo,
    keypoint badges) filled in with this product's real data. Layout/branding is
    pure compositing (zero hallucination risk); the optional background_photo and
    keypoint_icons are the only parts that come from an image-gen model, so a bad
    generation there degrades gracefully — a missing background falls back to a
    plain brand-color gradient, a missing icon falls back to a keyword-matched
    icon — instead of ever inventing the product itself.

    If full_scene_photo is given (an AI-composed shot that already places the
    product — optionally with a person using it — in its own environment),
    it's used as the entire card background and the separate boxed product
    photo is skipped, since the product is already part of that scene."""
    w, h = CARD_SIZE
    theme = _theme_colors(palette, dark_theme, custom_primary, custom_accent)
    safe = _framing_safe_insets(framing)

    if full_scene_photo is not None:
        card = _fit_on_blurred_canvas(full_scene_photo.convert("RGBA"), CARD_SIZE)
        # Clean up the top-left corner (reserved for the logo badge) before
        # any text/badges are drawn — the AI scene model's own attempt at
        # keeping that area "calm" often leaves a visible hazy box there
        # instead of blending naturally.
        _patch_dead_zone(card, theme["primary"], framing)
    elif background_photo is not None:
        # No tint/scrim at all — the background photo stays fully clear and
        # vivid, exactly as generated. Text legibility comes from the drop
        # shadow drawn behind each text line instead (see _draw_text below).
        card = _cover_crop(background_photo.convert("RGBA"), CARD_SIZE)
    else:
        card = _brand_gradient_background(theme)

    draw = ImageDraw.Draw(card)

    # Product title + tagline, top-right — sizes and column width measured
    # directly off the reference card (cap-height pixel scan), since the
    # previous sizes (40/24 over a 430px column) rendered far smaller and
    # wider than the reference's actual ~60/38 over a ~310px column.
    max_text_width = 380
    # A bold all-caps geometric sans set with zero tracking reads cramped
    # and heavy/stiff at large display sizes — a couple extra px between
    # letters is what real display typography does at this weight, and
    # threading it through the fit/wrap call too keeps the wrap decision
    # honest about the text's actual rendered width.
    title_letter_spacing = 2
    # Capped at 2 lines (not 3) so a long product name shrinks its font
    # instead of wrapping further down and dragging the tagline/keypoint
    # badges down with it — keeps the header block's height consistent
    # regardless of how many words the product name has.
    title_font, title_lines = _fit_title_font(
        draw, product_name.upper(), max_text_width, max_lines=2, font_theme=font_theme,
        letter_spacing=title_letter_spacing,
    )
    title_line_height = round(title_font.size * 1.35)
    # title_start_y respects this framing's own top-right safe inset (how
    # far down its border/badge artwork actually extends on the right half
    # of the card, where this right-aligned text lives) instead of the
    # full-width inset, which is driven by the top-left logo badge and used
    # to leave a big, unnecessary dead zone above the title on framings
    # where the logo doesn't reach anywhere near the right side.
    title_start_y = max(24, safe["top_right"] - 16)
    title_right_x = w - 40
    # Header block drawn directly with PIL, in fixed brand colors — title in
    # white, tagline in the palette's accent color (yellow for the default
    # navy/yellow palette) — instead of leaving color/position to an AI
    # typography pass, which drifted and picked inconsistent colors.
    _draw_right_aligned_shadowed_text(
        card, title_lines, title_font, title_right_x, title_start_y, title_line_height, WHITE,
        letter_spacing=title_letter_spacing,
    )
    y_cursor = title_start_y + len(title_lines) * title_line_height
    if tagline:
        # Scales down with the title (capped at 40px) so the title stays the
        # visually dominant, bigger line — but shrinks its own font first to
        # fit within 2 lines rather than ever silently dropping words off a
        # long AI-generated tagline (which used to read as a sentence cut
        # off mid-phrase, e.g. "Ringan Dan" with no continuation).
        tagline_start_size = max(28, min(48, round(title_font.size * 0.65)))
        tagline_font, tagline_lines = _fit_title_font(
            draw, tagline, max_text_width, max_lines=2, start_size=tagline_start_size,
            min_size=20, step=1, font_theme=font_theme, weight="medium",
        )
        # A visibly bigger gap under the title than the old flat +10 — that
        # read as the tagline crowding right up against the title instead
        # of sitting as its own distinct line.
        tagline_start_y = y_cursor + 22
        tagline_line_height = round(tagline_font.size * 1.35)
        _draw_right_aligned_shadowed_text(
            card, tagline_lines, tagline_font, title_right_x, tagline_start_y,
            tagline_line_height, theme["accent"],
        )
        y_cursor = tagline_start_y + len(tagline_lines) * tagline_line_height

    # Keypoint badges, right column — always 3 evenly-spaced fixed slots so the
    # layout looks identical whether a product has 1, 2, or 3 real keypoints;
    # slots beyond what the data supports are simply left empty, never faked.
    # Each row is icon-circle-on-the-left + label-to-its-right (matching the
    # approved reference card in assets/key point cell.png), not the older
    # icon-above/label-centered-below arrangement.
    badge_radius = 44
    slot_count = 3
    label_gap = 18
    row_right_x = w - max(40, safe["right"])
    row_left_x = max(560, row_right_x - 380)
    badge_cx = row_left_x + badge_radius
    label_left_x = badge_cx + badge_radius + label_gap
    label_max_width = max(120, row_right_x - label_left_x)

    if full_scene_photo is None:
        # Product photo, center-left — starts safely below the header text block.
        # Small gap and a bottom bound close to the card edge, matching how far
        # down the reference card's product photo actually extends (~950px of
        # 1024) — the old 40px gap + h-120 bound left the photo noticeably
        # smaller than the reference now that the header text is bigger/bolder.
        # Right edge stops with real margin before the badge column (row_left_x)
        # instead of the old fixed w-300 — that landed well past where the
        # badge circles start whenever this framing's safe margins pushed the
        # badge column further left, letting a wide product photo visually
        # collide with/underlap the badges instead of sitting cleanly beside
        # them.
        photo_top = max(240, y_cursor + 15)
        photo_right = min(w - 300, row_left_x - 30)
        _paste_fitted_photo(card, photo, (80, photo_top, photo_right, h - max(110, safe["bottom"] + 32)))
    # Starts right under the header text with just a small gap — the old
    # 387px fixed floor left a big dead zone above the badges whenever the
    # title/tagline were short, making the whole badge column read as
    # pushed down toward the bottom of the card instead of sitting close to
    # the header. Still drops lower when a long product name pushes the
    # title/tagline block further down, so the first badge never collides
    # with the tagline text.
    start_y = max(300, y_cursor + 34 + badge_radius)
    bottom_limit = h - max(130, safe["bottom"] + 36)
    row_margin = 20

    def _layout_labels(label_start_size: int) -> tuple[list[tuple[ImageFont.FreeTypeFont, list[str]]], int, int]:
        # Each label shrinks its own font (down to a floor) to stay within 2
        # lines rather than ever silently dropping a word — a fixed-size
        # font used to just truncate the wrapped line list to 2, which
        # could cut the end off a longer keypoint phrase entirely.
        specs = [
            _fit_title_font(
                draw, kp, label_max_width, max_lines=2, start_size=label_start_size,
                min_size=22, step=1, font_theme=font_theme, weight="medium",
            ) if kp else (_font("medium", label_start_size, font_theme), [])
            for kp in keypoints[:slot_count]
        ]
        lines = max((len(l) for _, l in specs), default=1) or 1
        line_height = max(
            (round(font.size * 1.25) for font, l in specs if l), default=round(label_start_size * 1.25),
        )
        # Label sits beside the circle now, not below it — a row's height is
        # whichever is taller: the circle itself (2.6x its radius, not a
        # flat 2x — leaves room for the badge's own soft outer glow, which
        # bleeds well past its plain edge; a tighter block clipped/merged
        # that glow into the row above/below it), or the (possibly 2-line)
        # label text.
        block_height = max(badge_radius * 2.6, lines * line_height)
        return specs, block_height, line_height

    # Row-to-row spacing (center to center) must clear whichever is taller —
    # the circle or the label block — plus a visible breathing-room margin.
    # If the full-size (36px) labels don't leave room for that within the
    # card, shrink the label font a step at a time (instead of immediately
    # crushing the spacing back down to a cramped minimum) — a slightly
    # smaller but comfortably-spaced label reads far more professional than
    # a full-size one it's nearly touching.
    label_specs, row_block_height, _ = _layout_labels(36)
    spacing = row_block_height + row_margin
    for label_start_size in range(35, 21, -1):
        if start_y + 2 * spacing + row_block_height / 2 <= bottom_limit:
            break
        label_specs, row_block_height, _ = _layout_labels(label_start_size)
        spacing = row_block_height + row_margin
    # Last-resort safety net for pathologically long headers: compress the
    # spacing itself, but never below the row's own measured height — going
    # tighter than that would recreate the exact row-overlap problem this is
    # meant to prevent.
    default_last_row_bottom = start_y + 2 * spacing + row_block_height / 2
    if default_last_row_bottom > bottom_limit:
        max_spacing = (bottom_limit - start_y - row_block_height / 2) / 2
        spacing = max(row_block_height, max_spacing)
    for i in range(slot_count):
        if i >= len(keypoints):
            continue
        keypoint = keypoints[i]
        cy = start_y + i * spacing
        # Glossy gradient-filled circle (soft shadow + radial gradient +
        # glass highlight) in the theme's deeper "badge" shade, rather than
        # a flat solid fill — a plain flat circle reads as a cheap
        # programmer-drawn shape next to the AI-generated photo; the
        # gradient/shadow/highlight combination is what actually reads as
        # a designed, premium badge. Uses "badge" rather than the plain
        # primary color because on a dark card the primary color IS the
        # background gradient's own dark stop, so a primary-filled circle
        # read as flat/washed-out instead of a distinct badge.
        _draw_glossy_badge(card, badge_cx, cy, badge_radius, theme["badge"], theme["ink"])
        generated_icon = keypoint_icons[i] if keypoint_icons and i < len(keypoint_icons) else None
        if generated_icon is not None:
            _composite_icon_image(card, generated_icon, badge_cx, cy, badge_radius * 0.48)
        else:
            _pick_icon(keypoint)(card, draw, badge_cx, cy, badge_radius * 0.48, theme["primary"])
        # Drawn directly with PIL (not left to the AI typography pass below) so
        # the label always sits at this exact spot, to the right of the circle
        # and vertically centered against it — deterministic pixel math
        # instead of an AI guess that could drift or land off-center.
        label_font, label_lines = label_specs[i]
        label_line_height = round(label_font.size * 1.25)
        label_top_y = round(cy - len(label_lines) * label_line_height / 2)
        _draw_left_aligned_shadowed_text(
            card, label_lines, theme["ink"], label_font, label_left_x, label_top_y, label_line_height,
        )

    # Title, tagline, and keypoint labels are all drawn deterministically
    # above now, so there's no text left for an AI typography pass to add —
    # just paste the border/logo badge on top and we're done.
    framing_image = _load_framing_image(framing)
    card.alpha_composite(framing_image)

    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


_DIMENSION_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[x×X]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm|m|inch|in)?"
)


def _parse_dimensions(ukuran: str) -> tuple[str, str] | None:
    """Pull a "W x H" pair out of a free-text UKURAN value (e.g. "14 x 4.5
    cm") for the schematic dimension diagram — returns None (diagram skipped)
    if it doesn't look like a plain two-number dimension string, rather than
    guessing at a format that isn't actually there."""
    match = _DIMENSION_PATTERN.search(ukuran or "")
    if not match:
        return None
    width_num, height_num, unit = match.group(1), match.group(2), match.group(3) or ""
    suffix = f" {unit}" if unit else ""
    return f"{width_num}{suffix}", f"{height_num}{suffix}"


def _draw_dimension_diagram(
    card: Image.Image, draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], dims: tuple[str, str],
    primary: tuple[int, int, int] = NAVY,
) -> None:
    """A small schematic box with width/height callout lines, the same idea
    as the reference card's dimension diagram — drawn generically from
    whatever numbers UKURAN actually contains, not a fixed illustration."""
    left, top, right, bottom = box
    draw.rounded_rectangle([left, top, right, bottom], radius=16, fill=WHITE)

    width_label, height_label = dims
    dim_font = _font("medium", 22)

    rect_left = left + 26
    rect_top = top + 22
    rect_right = right - 70
    rect_bottom = bottom - 48
    draw.rounded_rectangle([rect_left, rect_top, rect_right, rect_bottom], radius=8, outline=primary, width=3)

    # Width callout: horizontal line + end ticks under the box, label centered below.
    line_y = rect_bottom + 14
    draw.line([(rect_left, line_y), (rect_right, line_y)], fill=primary, width=2)
    draw.line([(rect_left, line_y - 5), (rect_left, line_y + 5)], fill=primary, width=2)
    draw.line([(rect_right, line_y - 5), (rect_right, line_y + 5)], fill=primary, width=2)
    label_w = draw.textlength(width_label, font=dim_font)
    draw.text(((rect_left + rect_right) / 2 - label_w / 2, line_y + 8), width_label, font=dim_font, fill=primary)

    # Height callout: vertical line + end ticks right of the box, label to the right.
    line_x = rect_right + 14
    draw.line([(line_x, rect_top), (line_x, rect_bottom)], fill=primary, width=2)
    draw.line([(line_x - 5, rect_top), (line_x + 5, rect_top)], fill=primary, width=2)
    draw.line([(line_x - 5, rect_bottom), (line_x + 5, rect_bottom)], fill=primary, width=2)
    draw.text((line_x + 8, (rect_top + rect_bottom) / 2 - dim_font.size / 2), height_label, font=dim_font, fill=primary)


def compose_spec_card(
    product_name: str,
    spec: dict[str, str],
    photo: Image.Image,
    background_photo: Image.Image | None = None,
    full_scene_photo: Image.Image | None = None,
    font_theme: str = _DEFAULT_FONT_THEME,
    palette: str = DEFAULT_PALETTE,
    dark_theme: bool = True,
    custom_primary: str | None = None,
    custom_accent: str | None = None,
    manual_text: str | None = None,
    framing: str = DEFAULT_FRAMING,
) -> bytes:
    """Render the spec-sheet card: product photo on the left, brand header,
    an optional dimension diagram, and the spec fields (MEREK/TIPE/ITEM NAME/
    UKURAN/MATERIAL/MADE IN/ISI KEMASAN) on the right — same fixed brand
    template approach as the keypoint card, so only real data ever appears.

    If full_scene_photo is given (the same AI-composed "product positioned in
    its own environment" shot used by the keypoint/usage cards' "AI atur
    posisi & scene" option), it fills the entire card instead of the plain
    boxed product photo — the spec fields still overlay on top of it.

    If manual_text is given, it replaces the AI-derived MEREK/TIPE/etc. field
    list entirely — each non-empty line the user typed is rendered as its own
    row, free-form, instead of the fixed "LABEL: value" layout (and `spec` is
    ignored)."""
    w, h = CARD_SIZE
    theme = _theme_colors(palette, dark_theme, custom_primary, custom_accent)
    safe = _framing_safe_insets(framing)
    if full_scene_photo is not None:
        card = _fit_on_blurred_canvas(full_scene_photo.convert("RGBA"), CARD_SIZE)
    elif background_photo is not None:
        card = _cover_crop(background_photo.convert("RGBA"), CARD_SIZE)
    else:
        card = _brand_gradient_background(theme)
    draw = ImageDraw.Draw(card)

    left_margin = max(60, safe["left"])
    eyebrow_y = max(150, safe["top"] - 34)
    title_start_y = max(184, safe["top"])
    title_font = _font("bold", 44, font_theme)
    title_lines = _wrap_text(draw, product_name.upper(), title_font, w - 120)[:2]
    title_y = title_start_y + len(title_lines) * round(title_font.size * 1.3)
    tagline = (spec.get("tagline") or "").strip() if not manual_text else ""
    deskripsi = (spec.get("deskripsi") or "").strip() if not manual_text else ""
    tagline_y = title_y + 6
    text_instructions = [
        f"Keep all text within the safe interior area of this {w}x{h}px image — at least "
        f"{safe['top']}px from the top edge, {safe['bottom']}px from the bottom edge, "
        f"{safe['left']}px from the left edge, and {safe['right']}px from the right edge. "
        "This card has a decorative brand frame/logo badge along its edges (added after "
        "your text), and any text placed outside that safe area risks being covered by it.",
        f"- Small eyebrow label \"SPESIFIKASI PRODUK\" at {_pos_pct(left_margin, eyebrow_y)}, "
        "above the product title.",
        f"- Product title \"{product_name.upper()}\": large bold headline starting at "
        f"{_pos_pct(left_margin, title_start_y)}.",
    ]
    if tagline:
        text_instructions.append(
            f"- Tagline \"{tagline}\": one line, smaller and lighter weight than the title, "
            f"directly beneath it at {_pos_pct(left_margin, tagline_y)}."
        )
    deskripsi_y = tagline_y + 40 if tagline else title_y + 20
    if deskripsi:
        text_instructions.append(
            f"- Short description paragraph \"{deskripsi}\": 2-3 lines, small regular weight "
            f"text, directly beneath the tagline at {_pos_pct(left_margin, deskripsi_y)}."
        )

    content_top = deskripsi_y + 70 if deskripsi else (tagline_y + 40 if tagline else title_y + 20)
    bottom_limit = h - max(110, safe["bottom"] + 32)
    if full_scene_photo is None:
        _paste_fitted_photo(card, photo, (left_margin, content_top, 560, bottom_limit))

    spec_x = max(600, left_margin + 540)
    spec_right_margin = max(40, safe["right"])
    spec_max_width = w - spec_right_margin - spec_x

    dims = _parse_dimensions(spec.get("ukuran", ""))
    spec_y = content_top
    if dims is not None:
        # Bigger than the old 210px box — was leaving a visibly empty strip
        # under the diagram since the photo column next to it runs much
        # taller, and this card otherwise has a lot of dead space at the
        # bottom.
        diagram_box = (spec_x, content_top, w - spec_right_margin, content_top + 260)
        _draw_dimension_diagram(card, draw, diagram_box, dims, theme["primary"])
        spec_y = diagram_box[3] + 30

    spec_font = _font("bold", 33, font_theme)
    if manual_text:
        # Pure free-form: whatever the user typed, one row per non-empty
        # line, no imposed "LABEL: value" structure.
        raw_lines = [line.strip() for line in manual_text.splitlines() if line.strip()]
    else:
        all_spec_lines = [
            ("ITEM NAME", spec.get("item_name", "-")),
            ("UKURAN", spec.get("ukuran", "-")),
            ("MATERIAL", spec.get("material", "-")),
            ("RING & BUCKLE", spec.get("ring_buckle", "-")),
            ("KAPASITAS", spec.get("kapasitas", "-")),
            ("APLIKASI", spec.get("aplikasi", "-")),
        ]
        # Skip fields the AI couldn't actually fill in — a row that just reads
        # "TIPE / JENIS: -" looks like broken/empty text rather than useful
        # spec info, and this card is only supposed to show real data anyway.
        spec_lines = [(label, value) for label, value in all_spec_lines if value and value.strip() not in ("", "-")]
        raw_lines = [f"{label}: {value}" for label, value in spec_lines]
    wrapped_line_counts = [len(_wrap_text(draw, line, spec_font, spec_max_width)[:2]) for line in raw_lines]
    # Stretch the gap between spec rows to actually reach down toward the
    # card's bottom edge instead of clustering at the top and leaving a big
    # empty strip below — capped so a short spec list doesn't end up looking
    # comically spaced out either.
    base_gap = 10
    natural_height = sum(count * round(spec_font.size * 1.3) + base_gap for count in wrapped_line_counts)
    available_height = max(0, bottom_limit - spec_y)
    extra_gap = max(0, min(18, (available_height - natural_height) / max(1, len(wrapped_line_counts))))

    for line, count in zip(raw_lines, wrapped_line_counts):
        text_instructions.append(f"- Spec row \"{line}\": at {_pos_pct(spec_x, spec_y)}.")
        spec_y += count * round(spec_font.size * 1.3) + base_gap + extra_gap

    # Border + logo badge, pasted before the AI text pass so the AI can see
    # its real shape/position and place text around it — then re-pasted after,
    # crisp, as a safety net in case the edit altered that region. When the
    # background came from the AI scene model, its own attempt at keeping
    # the top-left corner "calm" for the logo often leaves a visible hazy
    # box there instead of blending naturally, so patch it first.
    if full_scene_photo is not None:
        _patch_dead_zone(card, theme["primary"], framing)
    framing_image = _load_framing_image(framing)
    card.alpha_composite(framing_image)
    card = _ai_add_typography(card, "\n".join(text_instructions), framing)
    card.alpha_composite(framing_image)

    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _circle_crop(image: Image.Image, diameter: int) -> Image.Image:
    """Cover-crop an image into a filled circle of the given diameter, for
    the numbered step thumbnails on the usage card."""
    square = _cover_crop(image.convert("RGB"), (diameter, diameter))
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    result = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    result.paste(square, (0, 0))
    result.putalpha(mask)
    return result


def _rounded_square_crop(image: Image.Image, size: int, radius: int) -> Image.Image:
    """Cover-crop an image into a filled rounded square of the given size,
    for the usage card's numbered step thumbnails (matches the brand's own
    reference callout style — a rounded square photo with a corner number
    badge — instead of a plain circle)."""
    square = _cover_crop(image.convert("RGB"), (size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(square, (0, 0))
    result.putalpha(mask)
    return result


def compose_usage_card(
    product_name: str,
    photo: Image.Image,
    steps: list[dict[str, Any]],
    subtitle: str = "",
    background_photo: Image.Image | None = None,
    full_scene_photo: Image.Image | None = None,
    font_theme: str = _DEFAULT_FONT_THEME,
    palette: str = DEFAULT_PALETTE,
    dark_theme: bool = True,
    custom_primary: str | None = None,
    custom_accent: str | None = None,
    framing: str = DEFAULT_FRAMING,
) -> bytes:
    """Render the "cara penggunaan" card: a heading + one-sentence subtitle,
    a hero product photo, then a footer strip with up to 4 numbered step
    thumbnails, each with a bold title and a short supporting description.
    Each step is {"caption": str, "desc": str, "image": Image | None} — a
    missing per-step image (best-effort AI generation can fail) falls back
    to the plain product cutout in that slot instead of leaving it blank.

    If full_scene_photo is given (the same AI-composed "product positioned in
    its own environment" shot used by the keypoint card's "AI atur posisi &
    scene" option), it fills the entire card as the hero instead of the plain
    boxed cutout — the footer step strip still overlays on top of it."""
    w, h = CARD_SIZE
    theme = _theme_colors(palette, dark_theme, custom_primary, custom_accent)
    safe = _framing_safe_insets(framing)
    if full_scene_photo is not None:
        card = _fit_on_blurred_canvas(full_scene_photo.convert("RGBA"), CARD_SIZE)
        # Clean up the top-left corner (reserved for the logo badge) before
        # any text is drawn on top of it — the AI scene model's own attempt
        # at keeping that area "calm" often leaves a visible hazy box there
        # instead of blending naturally. Must happen before the heading
        # below, not after, or this would blur out the real heading text
        # too instead of just the background underneath it.
        _patch_dead_zone(card, theme["primary"], framing)
    elif background_photo is not None:
        card = _cover_crop(background_photo.convert("RGBA"), CARD_SIZE)
    else:
        card = _brand_gradient_background(theme)
    draw = ImageDraw.Draw(card)

    left_margin = max(60, safe["left"])
    right_margin = max(60, safe["right"])

    # Heading metrics computed up front (fixed, always-2-word Indonesian
    # label, not per-product data) so the hero/footer geometry below and the
    # legibility scrim can both be laid out before any pixels are drawn.
    heading_y = max(150, safe["top"])
    heading_font = _font("bold", 44, font_theme)
    heading_letter_spacing = 1.5
    heading_lines = ["CARA", "PENGGUNAAN"]
    heading_line_height = round(heading_font.size * 1.15)
    heading_bottom_y = heading_y + len(heading_lines) * heading_line_height

    # Shrink-to-fit rather than wrap-then-truncate — an oversized subtitle
    # must never silently lose its tail end; it's only ever allowed to get
    # smaller, never shorter. Same policy as _fit_title_font everywhere
    # else in this file.
    subtitle = (subtitle or "").strip()
    if subtitle:
        subtitle_font, subtitle_lines = _fit_title_font(
            draw, subtitle, w - left_margin - right_margin, max_lines=2, start_size=24, min_size=16,
            step=1, font_theme=font_theme, weight="regular",
        )
    else:
        subtitle_font = _font("regular", 24, font_theme)
        subtitle_lines = []
    subtitle_line_height = round(subtitle_font.size * 1.35)
    subtitle_y = heading_bottom_y + 14
    subtitle_bottom_y = subtitle_y + len(subtitle_lines) * subtitle_line_height if subtitle_lines else heading_bottom_y

    hero_top = subtitle_bottom_y + 24

    # Caption typography (bold step title + a shorter supporting
    # description beneath it) sized up front, against the longest title/
    # longest description across all 4 steps rather than each step
    # independently — keeps all 4 slots reading at the same visual weight
    # instead of one shrinking while its neighbors stay full-size.
    slot_count = 4
    circle_r = 76
    number_font = _font("bold", 22, font_theme)
    slot_w = (w - left_margin - right_margin) / slot_count
    caption_max_width = slot_w - 20
    titles = [
        (steps[i].get("caption", "") if i < len(steps) and steps[i] else "") for i in range(slot_count)
    ]
    descs = [
        (steps[i].get("desc", "") if i < len(steps) and steps[i] else "") for i in range(slot_count)
    ]
    # Shrink-to-fit against the longest title/description (not wrap-then-
    # truncate) — the reserved footer height below is driven by however
    # many lines that actually takes, so a caption never gets its tail cut
    # off; worst case the footer grows a bit taller instead of losing text.
    longest_title = max(titles, key=len, default="")
    if longest_title:
        title_font, title_fit_lines = _fit_title_font(
            draw, longest_title, caption_max_width, max_lines=2, start_size=22, min_size=14,
            step=1, font_theme=font_theme, weight="bold",
        )
        title_lines_count = len(title_fit_lines)
    else:
        title_font = _font("bold", 22, font_theme)
        title_lines_count = 0
    title_line_height = round(title_font.size * 1.2)

    longest_desc = max(descs, key=len, default="")
    if longest_desc:
        desc_font, desc_fit_lines = _fit_title_font(
            draw, longest_desc, caption_max_width, max_lines=2, start_size=17, min_size=12,
            step=1, font_theme=font_theme, weight="regular",
        )
        desc_lines_count = len(desc_fit_lines)
    else:
        desc_font = _font("regular", 17, font_theme)
        desc_lines_count = 0
    desc_line_height = round(desc_font.size * 1.3)

    # Footer height reserves room for however many lines the title/desc fit
    # actually needed (see above — never a hardcoded "2 lines" guess), so it
    # always lands above this framing's own bottom safe inset — a brand
    # with a bigger bottom border/tab (e.g. Ladder Bro) needs more room
    # here than GOSAVE's thin bottom edge, and a caption that ended up
    # needing more than 2 lines still gets the room it actually needs.
    caption_block_h = (
        title_lines_count * title_line_height
        + (6 if title_lines_count and desc_lines_count else 0)
        + desc_lines_count * desc_line_height
    )
    footer_h = 30 + circle_r * 2 + 14 + caption_block_h + max(78, safe["bottom"] + 54)
    hero_bottom = h - footer_h - 20
    footer_top = hero_bottom + 20

    # No solid/gradient panel behind the heading or the footer strip — a
    # flat color rectangle sitting on top of the photo read as a stray
    # colored box/shadow behind the text rather than a clean card. Every
    # piece of text here relies only on its own per-letter drop shadow
    # (see _draw_left_aligned_shadowed_text / _draw_centered_shadowed_text)
    # for contrast; the AI scene prompt already keeps the top and bottom
    # strips of the photo calm/plain so that shadow alone is enough.
    photo_backed = full_scene_photo is not None or background_photo is not None
    footer_text_color = WHITE if photo_backed else theme["ink"]
    # Over a real photo, force white/accent instead of `ink` (which is
    # picked for contrast against the theme's own *gradient* background,
    # and on a light palette like GOTO can itself be a color with poor
    # contrast against a photo).
    heading_colors = [WHITE, theme["accent"]] if photo_backed else [theme["ink"], theme["ink_accent"]]

    # Two-tone (ink / accent) matches the bold two-color headline style of
    # the reference brand cards; drawn directly with PIL (not the AI
    # typography pass) for an exact position and color every time.
    _draw_left_aligned_shadowed_text(
        card, heading_lines, heading_colors, heading_font,
        left_margin, heading_y, heading_line_height, letter_spacing=heading_letter_spacing,
    )
    if subtitle_lines:
        subtitle_color = WHITE if photo_backed else _lighten(theme["ink"], 0.35)
        _draw_left_aligned_shadowed_text(
            card, subtitle_lines, subtitle_color, subtitle_font, left_margin, subtitle_y, subtitle_line_height,
        )

    if full_scene_photo is None:
        _paste_fitted_photo(card, photo, (left_margin, hero_top, w - right_margin, hero_bottom))

    desc_text_color = _darken(WHITE, 0.22) if photo_backed else _lighten(theme["ink"], 0.35)

    for i in range(slot_count):
        cx = left_margin + slot_w * (i + 0.5)
        cy = footer_top + 30 + circle_r

        step = steps[i] if i < len(steps) else None
        step_image = step.get("image") if step else None
        if step_image is not None:
            source_image = step_image
        else:
            # Fallback slot: flatten the (likely transparent) product cutout
            # onto white first, so convert("RGB") inside _circle_crop doesn't
            # turn the transparent margin into black.
            flattened = Image.new("RGB", photo.size, WHITE)
            flattened.paste(photo.convert("RGBA"), (0, 0), photo.convert("RGBA"))
            source_image = flattened
        thumb_size = round(circle_r * 2)
        thumb_radius = round(thumb_size * 0.22)
        thumb_left, thumb_top = round(cx - circle_r), round(cy - circle_r)
        thumb = _rounded_square_crop(source_image, thumb_size, thumb_radius)
        card.alpha_composite(thumb, (thumb_left, thumb_top))
        draw.rounded_rectangle(
            [thumb_left, thumb_top, thumb_left + thumb_size, thumb_top + thumb_size],
            radius=thumb_radius, outline=WHITE, width=4,
        )

        badge_size = 40
        badge_radius = 10
        badge_left = thumb_left + thumb_size - badge_size * 0.68
        badge_top = thumb_top + thumb_size - badge_size * 0.68
        draw.rounded_rectangle(
            [badge_left, badge_top, badge_left + badge_size, badge_top + badge_size],
            radius=badge_radius, fill=theme["primary"], outline=WHITE, width=2,
        )
        number = str(i + 1)
        number_w = draw.textlength(number, font=number_font)
        draw.text(
            (badge_left + badge_size / 2 - number_w / 2, badge_top + badge_size / 2 - number_font.size / 2 - 2),
            number, font=number_font, fill=WHITE,
        )

        text_y = cy + circle_r + 14
        # Not sliced to [:2] — title_font/desc_font were already sized so
        # the LONGEST title/desc across all 4 steps fits within 2 lines, so
        # every individual step's own (shorter-or-equal) text wraps to that
        # many lines or fewer, never needing truncation.
        title_lines = _wrap_text(draw, titles[i], title_font, caption_max_width) if titles[i] else []
        if title_lines:
            _draw_centered_shadowed_text(
                card, title_lines, title_font, cx, text_y, title_line_height, footer_text_color,
            )
            text_y += len(title_lines) * title_line_height + 6
        desc_lines = _wrap_text(draw, descs[i], desc_font, caption_max_width) if descs[i] else []
        if desc_lines:
            _draw_centered_shadowed_text(
                card, desc_lines, desc_font, cx, text_y, desc_line_height, desc_text_color,
            )

    # Border + logo badge pasted on top last, exact real pixels every time —
    # nothing below this point is AI-generated, so there's no "re-paste as a
    # safety net" step needed anymore.
    framing_image = _load_framing_image(framing)
    card.alpha_composite(framing_image)

    buffer = io.BytesIO()
    card.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()
