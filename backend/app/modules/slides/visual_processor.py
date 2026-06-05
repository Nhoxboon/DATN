"""Visual candidate and image materialization helpers for slide decks."""

from __future__ import annotations

import base64
import io
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

from app.core.document_naming import safe_pdf_storage_path
from app.modules.slides.constants import (
    COMPONENT_LAYOUTS,
    MAX_SOURCE_CROPS_PER_DECK,
    MIN_CROP_CONFIDENCE,
    SOURCE_VISUAL_PROMOTION_THRESHOLD,
    SOURCE_VISUAL_STOPWORDS,
    VISUAL_LAYOUTS,
)
from app.modules.slides.models import CropBox, CropSelectionPayload
from app.modules.slides.payload_utils import _parse_json_object
from app.modules.slides.text_utils import (
    _first_page_from_range,
    _int_or_none,
    _normalized_label,
    _truncate_words,
    _visible_strings,
)


logger = logging.getLogger(__name__)


def _materialize_visuals(
    *,
    deck: dict[str, Any],
    genai_client: genai.Client,
    image_model: str,
    client: Any,
    settings: Any,
    user_id: str,
    notebook_id: str,
    visual_candidates: list[dict[str, Any]],
    crop_model: str | None = None,
) -> dict[str, Any]:
    """Attach small preview image data URLs for selected visuals."""
    slides = deck.get("slides")
    if not isinstance(slides, list):
        return deck

    max_generated_images = 1
    generated_count = 0
    source_crop_count = 0
    candidates_by_source = {
        int(candidate["source_index"]): candidate for candidate in visual_candidates if "source_index" in candidate
    }

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        visual = slide.get("visual")
        if not isinstance(visual, dict):
            visual = {}
            slide["visual"] = visual
        anchor = _slide_visual_anchor(slide)
        kind = anchor.get("kind") or visual.get("kind")
        layout = str(slide.get("layout_type") or "")
        if layout == "VISUAL_ANCHOR" and kind in {"icon", "none", None, ""}:
            promoted_candidate = _best_source_visual_candidate_for_slide(slide, visual_candidates)
            if promoted_candidate:
                anchor.update(
                    {
                        "kind": "source_page",
                        "source_index": promoted_candidate.get("source_index"),
                        "page": promoted_candidate.get("page"),
                        "alt": anchor.get("alt") or slide.get("title"),
                    }
                )
                visual.update(
                    {
                        "kind": "source_page",
                        "source_index": promoted_candidate.get("source_index"),
                        "page": promoted_candidate.get("page"),
                        "alt": anchor.get("alt") or slide.get("title"),
                    }
                )
                kind = "source_page"
        if kind in {"source_page", "generated_image"} and layout in COMPONENT_LAYOUTS and layout not in VISUAL_LAYOUTS:
            visual["kind"] = "none"
            anchor["kind"] = "none"
            continue
        if kind == "source_page":
            if visual.get("kind") != "source_page":
                visual.update(
                    {
                        "kind": "source_page",
                        "source_index": anchor.get("source_index"),
                        "page": anchor.get("page"),
                        "alt": anchor.get("alt"),
                    }
                )
            data_url, crop_box = _source_visual_data_and_crop(
                client=client,
                settings=settings,
                user_id=user_id,
                notebook_id=notebook_id,
                visual=visual if visual.get("source_index") else anchor,
                candidates_by_source=candidates_by_source,
                genai_client=genai_client,
                crop_model=crop_model,
                crop_enabled=source_crop_count < MAX_SOURCE_CROPS_PER_DECK,
                crop_hint=_slide_crop_hint(slide),
            )
            if data_url:
                visual["data_url"] = data_url
                anchor["data_url"] = data_url
                if crop_box:
                    visual["crop_box"] = crop_box
                    anchor["crop_box"] = crop_box
                    source_crop_count += 1
            else:
                visual["kind"] = "none"
                anchor["kind"] = "none"
        elif kind == "generated_image":
            if generated_count >= max_generated_images:
                visual["kind"] = "none"
                anchor["kind"] = "none"
                continue
            if visual.get("kind") != "generated_image":
                visual.update({"kind": "generated_image", "prompt": anchor.get("prompt"), "alt": anchor.get("alt")})
            prompt = str(anchor.get("prompt") or visual.get("prompt") or "").strip()
            if not prompt:
                prompt = f"Minimal academic presentation visual for: {slide.get('title', 'key idea')}"
            data_url = _generate_image_data_url(genai_client, image_model, prompt)
            if data_url:
                visual["data_url"] = data_url
                anchor["data_url"] = data_url
                generated_count += 1
            else:
                visual["kind"] = "none"
                anchor["kind"] = "none"

    deck["image_generation_count"] = generated_count
    deck["source_crop_count"] = source_crop_count
    return deck


def _slide_visual_anchor(slide: dict[str, Any]) -> dict[str, Any]:
    components = slide.get("components") if isinstance(slide.get("components"), dict) else {}
    anchor = components.get("visual_anchor") if isinstance(components.get("visual_anchor"), dict) else None
    if anchor is None:
        anchor = {}
        components["visual_anchor"] = anchor
        slide["components"] = components
    return anchor


def _slide_crop_hint(slide: dict[str, Any]) -> str:
    """Compact human-readable hint for selecting a crop from a source PDF page."""
    parts = [
        str(slide.get("title") or ""),
        str(slide.get("subtitle") or ""),
    ]
    visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
    anchor = _slide_visual_anchor(slide)
    parts.extend(
        [
            str(visual.get("alt") or ""),
            str(anchor.get("caption") or ""),
            str(anchor.get("alt") or ""),
        ]
    )
    components = slide.get("components") if isinstance(slide.get("components"), dict) else {}
    parts.extend(_visible_strings(components)[:10])
    return _truncate_words(" ".join(part for part in parts if part).strip(), 90)


def _best_source_visual_candidate_for_slide(
    slide: dict[str, Any],
    visual_candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not visual_candidates:
        return None
    hint = _slide_crop_hint(slide)
    hint_tokens = _source_visual_tokens(hint)
    if not hint_tokens:
        return None

    best_candidate: dict[str, Any] | None = None
    best_score = 0
    for candidate in visual_candidates:
        candidate_text = " ".join(
            str(candidate.get(key) or "")
            for key in ("document_name", "page_range", "excerpt")
        )
        candidate_tokens = _source_visual_tokens(candidate_text)
        score = len(hint_tokens & candidate_tokens)
        score += _source_visual_phrase_bonus(_normalized_label(hint), _normalized_label(candidate_text))
        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_score < SOURCE_VISUAL_PROMOTION_THRESHOLD:
        return None
    return best_candidate


def _source_visual_tokens(text: str) -> set[str]:
    normalized = _normalized_label(text)
    tokens = set(re.findall(r"[a-z0-9]+", normalized))
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in SOURCE_VISUAL_STOPWORDS
    }


def _source_visual_phrase_bonus(hint: str, candidate_text: str) -> int:
    bonus = 0
    related_groups = [
        ("profiler", ("profiler", "cpu", "gpu", "memory", "rendering", "timeline", "frame", "camera render", "gc alloc")),
        ("object pooling", ("objectpool", "object pooling", "pool", "bullet", "missile", "projectile")),
        ("physics", ("physics", "collision", "collider", "raycast", "layer", "matrix")),
        ("rendering", ("gpu", "rendering", "atlas", "mesh", "ui", "texture", "lighting")),
        ("localization", ("localization", "locale", "string table", "asset table", "addressables")),
    ]
    for anchor, terms in related_groups:
        if anchor not in hint:
            continue
        matches = sum(1 for term in terms if term in candidate_text)
        if matches:
            bonus += min(3, matches)
    return bonus


def _visual_candidates(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return chunks that can guide source visual reuse."""
    candidates: list[dict[str, Any]] = []
    for source_index, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        if not metadata.get("has_visual"):
            continue
        pages = chunk.get("pages") if isinstance(chunk.get("pages"), list) else []
        page = pages[0] if pages else _first_page_from_range(chunk.get("page_range"))
        candidates.append(
            {
                "source_index": source_index,
                "document_name": str(chunk.get("document_name") or ""),
                "page_range": str(chunk.get("page_range") or "unknown"),
                "page": page,
                "storage_path": metadata.get("storage_path"),
                "excerpt": _truncate_words(re.sub(r"\s+", " ", str(chunk.get("content") or "")).strip(), 64),
            }
        )
    return candidates


def _source_visual_data_url(
    *,
    client: Any,
    settings: Any,
    user_id: str,
    notebook_id: str,
    visual: dict[str, Any],
    candidates_by_source: dict[int, dict[str, Any]],
) -> str | None:
    data_url, _crop_box = _source_visual_data_and_crop(
        client=client,
        settings=settings,
        user_id=user_id,
        notebook_id=notebook_id,
        visual=visual,
        candidates_by_source=candidates_by_source,
        genai_client=None,
        crop_model=None,
        crop_enabled=False,
        crop_hint="",
    )
    return data_url


def _source_visual_data_and_crop(
    *,
    client: Any,
    settings: Any,
    user_id: str,
    notebook_id: str,
    visual: dict[str, Any],
    candidates_by_source: dict[int, dict[str, Any]],
    genai_client: genai.Client | None,
    crop_model: str | None,
    crop_enabled: bool,
    crop_hint: str,
) -> tuple[str | None, dict[str, float] | None]:
    source_index = _int_or_none(visual.get("source_index"))
    candidate = candidates_by_source.get(source_index or -1)
    if not candidate:
        return None, None

    page = _int_or_none(visual.get("page")) or _int_or_none(candidate.get("page")) or 1
    document_name = str(candidate.get("document_name") or "").strip()
    storage_path = candidate.get("storage_path")
    possible_paths = [
        Path(settings.uploads_dir) / user_id / notebook_id / safe_pdf_storage_path(document_name),
    ]

    for local_path in possible_paths:
        if local_path.exists():
            return _render_source_pdf_page_data_url(
                local_path,
                page,
                genai_client=genai_client,
                crop_model=crop_model,
                crop_enabled=crop_enabled,
                crop_hint=crop_hint,
            )

    storage_candidates = [storage_path] if isinstance(storage_path, str) and storage_path else []
    storage_candidates.append(f"{user_id}/{notebook_id}/{safe_pdf_storage_path(document_name)}")
    for path in dict.fromkeys(storage_candidates):
        with tempfile.TemporaryDirectory(prefix="datn-slide-source-") as temp_dir:
            local_path = Path(temp_dir) / "source.pdf"
            if _download_storage_object(client, "pdfs", path, local_path):
                return _render_source_pdf_page_data_url(
                    local_path,
                    page,
                    genai_client=genai_client,
                    crop_model=crop_model,
                    crop_enabled=crop_enabled,
                    crop_hint=crop_hint,
                )
    return None, None


def _download_storage_object(client: Any, bucket: str, storage_path: str, local_path: Path) -> bool:
    try:
        data = client.storage.from_(bucket).download(storage_path)
    except Exception:
        return False
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, bytes):
        return False
    local_path.write_bytes(data)
    return True


def _render_source_pdf_page_data_url(
    pdf_path: Path,
    page_number: int,
    *,
    genai_client: genai.Client | None,
    crop_model: str | None,
    crop_enabled: bool,
    crop_hint: str,
) -> tuple[str | None, dict[str, float] | None]:
    image = _render_pdf_page_image(pdf_path, page_number)
    if image is None:
        return None, None

    crop_box: CropBox | None = None
    if crop_enabled and genai_client is not None and crop_model:
        crop_box = _choose_source_crop_box(genai_client, crop_model, image, crop_hint)
        if crop_box is not None:
            image = _crop_image(image, crop_box)

    return _image_to_data_url(image), crop_box.model_dump() if crop_box else None


def _render_pdf_page_data_url(pdf_path: Path, page_number: int) -> str | None:
    image = _render_pdf_page_image(pdf_path, page_number)
    return _image_to_data_url(image) if image else None


def _render_pdf_page_image(pdf_path: Path, page_number: int) -> Image.Image | None:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        page_index = max(page_number - 1, 0)
        if page_index >= len(pdf):
            page_index = 0
        page = pdf[page_index]
        bitmap = page.render(scale=2.4)
        return bitmap.to_pil().convert("RGB")
    except Exception:
        logger.info("Could not render source PDF page for slide visual path=%s page=%s", pdf_path, page_number, exc_info=True)
        return None


def _choose_source_crop_box(
    genai_client: genai.Client,
    crop_model: str,
    image: Image.Image,
    crop_hint: str,
) -> CropBox | None:
    """Ask Gemini Vision for a grounded page crop; invalid/low confidence means whole page."""
    try:
        image_part = _image_part_for_crop(image)
        prompt = (
            "Return strict JSON only: {\"crop_box\":{\"x\":0.0,\"y\":0.0,\"width\":1.0,\"height\":1.0},"
            "\"confidence\":0.0,\"rationale\":\"short\"}. "
            "Choose the smallest useful normalized crop containing the visual evidence for this presentation slide. "
            "Prefer diagrams, charts, tables, profiler panels, code blocks, or illustrations. "
            "Avoid page title/footer/margins unless they are essential. Do not invent content. "
            "Use coordinates from the top-left of the page, normalized 0-1. "
            f"Slide purpose/content hint: {crop_hint[:700]}"
        )
        response = genai_client.models.generate_content(
            model=crop_model,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=512,
                response_mime_type="application/json",
            ),
        )
        payload = CropSelectionPayload.model_validate(_parse_json_object(str(response.text or "")))
        if payload.crop_box is None or payload.confidence < MIN_CROP_CONFIDENCE:
            return None
        return payload.crop_box
    except Exception:
        logger.info("Could not select crop box for source slide visual.", exc_info=True)
        return None


def _image_part_for_crop(image: Image.Image) -> types.Part:
    image_copy = image.copy()
    image_copy.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
    if image_copy.mode != "RGB":
        image_copy = image_copy.convert("RGB")
    buffer = io.BytesIO()
    image_copy.save(buffer, format="WEBP", quality=86)
    return types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/webp")


def _crop_image(image: Image.Image, crop_box: CropBox) -> Image.Image:
    width, height = image.size
    pad_x = crop_box.width * 0.025
    pad_y = crop_box.height * 0.025
    x1 = max(0, int(round((crop_box.x - pad_x) * width)))
    y1 = max(0, int(round((crop_box.y - pad_y) * height)))
    x2 = min(width, int(round((crop_box.x + crop_box.width + pad_x) * width)))
    y2 = min(height, int(round((crop_box.y + crop_box.height + pad_y) * height)))
    if x2 - x1 < 80 or y2 - y1 < 80:
        return image
    return image.crop((x1, y1, x2, y2))


def _generate_image_data_url(genai_client: genai.Client, image_model: str, prompt: str) -> str | None:
    image_prompt = (
        "Create a clean, modern academic presentation visual. "
        "No readable text, no logos, no watermarks, no UI chrome. "
        "Use restrained colors and generous whitespace. "
        f"Concept: {prompt}"
    )
    try:
        response = genai_client.models.generate_content(
            model=image_model,
            contents=image_prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )
        for candidate in response.candidates or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                inline_data = getattr(part, "inline_data", None)
                if not inline_data:
                    continue
                raw = inline_data.data
                image_bytes = raw if isinstance(raw, bytes) else base64.b64decode(raw)
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                return _image_to_data_url(image)
    except Exception:
        logger.info("Could not generate slide image with model=%s.", image_model, exc_info=True)
    return None


def _image_to_data_url(image: Image.Image, max_size: tuple[int, int] = (1800, 1012)) -> str:
    image = image.copy()
    image.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
