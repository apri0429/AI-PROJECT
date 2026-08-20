from __future__ import annotations

import json
import logging
import re

from config import settings

logger = logging.getLogger(__name__)

_client_error: str | None = None
_client = None

if settings.gemini_api_key:
    try:
        from google import genai
        from google.genai import types as genai_types

        _client = genai.Client(api_key=settings.gemini_api_key)
    except Exception as exc:  # pragma: no cover - defensive, depends on env
        _client_error = f"Gemini client unavailable: {exc}"
        logger.warning(_client_error)
else:
    _client_error = "GEMINI_API_KEY is not set"

def _square_image_config(temperature: float | None = None):
    """Square output enforced via the API's own aspect-ratio config — a text
    instruction like "must be square" is frequently ignored by the image
    model, which then needs cropping afterwards and risks cutting off the
    subject. This makes the model actually generate 1:1 in the first place.

    `temperature` is left at the model's own default (higher, more varied)
    for normal creative generation — only callers doing reference-matching
    work (a real example image attached, asked to replicate its layout)
    pass a low value, which biases the model toward its single most likely/
    literal interpretation of that reference instead of a creative
    reinterpretation of it. Doesn't make output pixel-identical (this is
    still a generative image model, not a template), but measurably
    tightens run-to-run consistency for that specific use case."""
    kwargs: dict = {"image_config": genai_types.ImageConfig(aspect_ratio="1:1")}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return genai_types.GenerateContentConfig(**kwargs)


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return text


def _generate(prompt: str, fallback_label: str) -> str:
    if _client is None:
        logger.info("Falling back to stub %s (%s)", fallback_label, _client_error)
        return f"[stub {fallback_label}, {_client_error}] {prompt[:80]}"

    try:
        response = _client.models.generate_content(model=settings.gemini_model, contents=prompt)
        text = (response.text or "").strip()
        return _strip_markdown(text) if text else "[Gemini returned an empty response]"
    except Exception as exc:  # pragma: no cover - network/API failure path
        logger.error("Gemini generation failed: %s", exc)
        return f"[Gemini error: {exc}]"


def generate_summary(prompt: str) -> str:
    return _generate(prompt, "summary")


def answer_question(prompt: str) -> str:
    return _generate(prompt, "answer")


def translate_text(prompt: str) -> str:
    return _generate(prompt, "translation")


def translate_document_part(prompt: str, data: bytes, mime_type: str) -> str:
    """Send a document (PDF page, or a plain image) directly to Gemini as a
    file part, not extracted text, alongside a translation prompt. Gemini
    reads the rendered content itself, so this also handles scanned/
    image-only pages that have no embedded, extractable text layer. Raises
    on failure — callers decide how to handle it."""
    if _client is None:
        raise RuntimeError(_client_error)

    part = genai_types.Part.from_bytes(data=data, mime_type=mime_type)
    response = _client.models.generate_content(
        model=settings.gemini_model, contents=[part, prompt],
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty translation")
    return text


def translate_pdf_document(prompt: str, pdf_bytes: bytes) -> str:
    return translate_document_part(prompt, pdf_bytes, "application/pdf")


def generate_json(prompt: str) -> dict:
    if _client is None:
        raise RuntimeError(_client_error)

    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty JSON response")
    return json.loads(response.text)


def generate_json_from_image(prompt: str, image_bytes: bytes) -> list | dict:
    """Same as generate_json, but grounded in an image — used for vision
    tasks like locating diagram/illustration regions on a scanned page
    rather than generating structured text content."""
    if _client is None:
        raise RuntimeError(_client_error)

    part = genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    response = _client.models.generate_content(
        model=settings.gemini_model,
        contents=[part, prompt],
        config={"response_mime_type": "application/json"},
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty JSON response")
    return json.loads(response.text)


def _extract_image_bytes(response) -> bytes:
    """Pull the inline image bytes out of a generate_content image response —
    shared by every image-generating call below so the "no image part" /
    "empty image data" guards only need to be gotten right in one place."""
    candidates = response.candidates or []
    if not candidates:
        raise RuntimeError("Gemini image response contained no candidates")
    content = candidates[0].content
    for part in (content.parts if content else None) or []:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data

    raise RuntimeError("Gemini image response contained no image data")


def generate_image_from_references(prompt: str, images: list[bytes], temperature: float | None = None) -> bytes:
    """Generate a new image grounded in one or more real reference photos
    (e.g. the product's real marketing photos) plus a text prompt — used to
    keep the product's actual appearance intact in an AI-generated usage
    scene, instead of edit_image's single-image case. Raises on failure —
    callers decide how to fall back.

    `temperature`: see _square_image_config — pass a moderate value (e.g.
    0.6-0.7) when one of the reference images is a style example the
    output should stay grounded in, without going so low the output barely
    varies between repeat calls with the same prompt/references."""
    if _client is None:
        raise RuntimeError(_client_error)

    parts = [
        genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png")
        for image_bytes in images
    ]
    parts.append(genai_types.Part.from_text(text=prompt))

    response = _client.models.generate_content(
        # `parts: list[Part]` vs. the SDK's own dynamically-built
        # PartUnionDict alias (its type varies by whether PIL is
        # importable, so pyright can't resolve it as a static type here)
        # — a stub-resolution mismatch only, not a real type error.
        model=settings.gemini_image_model, contents=parts, config=_square_image_config(temperature),  # type: ignore[reportArgumentType]
    )
    return _extract_image_bytes(response)


def generate_image(prompt: str) -> bytes:
    """Generate a single image from a text prompt using Gemini's image model.
    Raises on failure — callers decide how to fall back (e.g. a plain background)."""
    if _client is None:
        raise RuntimeError(_client_error)

    response = _client.models.generate_content(
        model=settings.gemini_image_model,
        contents=prompt,
        config=_square_image_config(),
    )
    return _extract_image_bytes(response)


def edit_image(prompt: str, image, aspect_ratio: str = "1:1") -> bytes:
    """Image-in, image-out edit — e.g. isolating just the main product shot
    out of a busy multi-photo marketplace listing image, which a fixed
    background-removal model can't do since it has no idea which region is
    "the product". Raises on failure — callers decide how to fall back.

    `aspect_ratio` defaults to the card's own square "1:1" (every other
    caller composites this output onto a fixed-size square card), but a
    caller editing a source reference photo that must keep its original
    proportions (e.g. isolating the product out of a non-square upload)
    should pass the ratio matching that photo's own real width/height —
    forcing every edit through a square canvas would otherwise stretch or
    reframe a portrait/landscape source photo away from its true shape."""
    if _client is None:
        raise RuntimeError(_client_error)

    kwargs: dict = {"image_config": genai_types.ImageConfig(aspect_ratio=aspect_ratio)}
    response = _client.models.generate_content(
        model=settings.gemini_image_model,
        contents=[image, prompt],
        config=genai_types.GenerateContentConfig(**kwargs),
    )
    return _extract_image_bytes(response)
