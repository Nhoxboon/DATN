"""Celery task for generating notebook slide decks."""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.config import get_app_config, get_settings
from app.core.document_naming import safe_pdf_storage_path
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.modules.slides.repository import get_slide_deck_repository
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)

MIN_SLIDES = 5
MAX_SLIDES = 12
MAX_CONTEXT_CHARS = 42000
BATCH_CONTEXT_CHARS = 6000
MAX_DECK_ATTEMPTS = 3
MAX_DECK_OUTPUT_TOKENS = 12000
MAX_WORDS_PER_SLIDE = 70
MAX_WORDS_PER_BULLET = 20
MAX_BULLETS_PER_SLIDE = 4
SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900
PDF_RENDER_SCALE = 2
BULLET_LIKE_LAYOUTS = {"KEY_BULLETS"}
VISUAL_LAYOUTS = {"TITLE", "FIGURE_FOCUS", "HIGHLIGHT_CARD"}
FINAL_SUMMARY_TITLES = {
    "tom tat",
    "tong ket",
    "ket luan",
    "summary",
    "recap",
    "conclusion",
    "takeaways",
    "key takeaways",
}
ALLOWED_LAYOUTS = {
    "TITLE",
    "KEY_BULLETS",
    "TWO_COLUMNS",
    "THREE_FEATURES",
    "BIG_STAT",
    "FIGURE_FOCUS",
    "SECTION_DIVIDER",
    "HIGHLIGHT_CARD",
    "TIMELINE",
}
CITATION_PATTERN = re.compile(r"\[(?:\d+(?:\s*,\s*\d+)*)\]")


class SlideVisual(BaseModel):
    """Visual instruction chosen by the deck planner."""

    kind: Literal["none", "source_page", "generated_image"] = "none"
    prompt: str | None = None
    source_index: int | None = None
    page: int | None = None
    alt: str | None = None
    data_url: str | None = None


class SlideFeature(BaseModel):
    """Feature item used by THREE_FEATURES slides."""

    title: str | None = None
    text: str | None = None


class SlideContent(BaseModel):
    """Layout-specific slide content with a schema Gemini can follow."""

    left_title: str | None = None
    right_title: str | None = None
    left: list[str] = Field(default_factory=list)
    right: list[str] = Field(default_factory=list)
    features: list[SlideFeature] = Field(default_factory=list)
    stat: str | None = None
    label: str | None = None
    context: str | None = None
    caption: str | None = None
    takeaway: str | None = None
    steps: list[SlideFeature] = Field(default_factory=list)


class SlidePayload(BaseModel):
    """One normalized slide returned by the LLM."""

    slide_number: int
    layout_type: Literal[
        "TITLE",
        "KEY_BULLETS",
        "TWO_COLUMNS",
        "THREE_FEATURES",
        "BIG_STAT",
        "FIGURE_FOCUS",
        "SECTION_DIVIDER",
        "HIGHLIGHT_CARD",
        "TIMELINE",
    ]
    title: str = ""
    subtitle: str | None = None
    bullets: list[str] = Field(default_factory=list)
    content: SlideContent = Field(default_factory=SlideContent)
    visual: SlideVisual = Field(default_factory=SlideVisual)

    @field_validator("bullets")
    @classmethod
    def validate_bullets(cls, bullets: list[str]) -> list[str]:
        if len(bullets) > MAX_BULLETS_PER_SLIDE:
            raise ValueError(f"Each slide may contain at most {MAX_BULLETS_PER_SLIDE} bullets.")
        for bullet in bullets:
            if _word_count(bullet) > MAX_WORDS_PER_BULLET:
                raise ValueError(f"Bullet exceeds {MAX_WORDS_PER_BULLET} words: {bullet}")
            if CITATION_PATTERN.search(bullet):
                raise ValueError("Visible citations are not allowed in slide content.")
        return bullets

    @model_validator(mode="after")
    def validate_slide_text(self) -> "SlidePayload":
        visible_text = _visible_strings(
            {
                "title": self.title,
                "subtitle": self.subtitle,
                "bullets": self.bullets,
                "content": self.content.model_dump(),
            }
        )
        for text in visible_text:
            if CITATION_PATTERN.search(text):
                raise ValueError("Visible citations are not allowed in slide content.")
        total_words = sum(_word_count(text) for text in visible_text)
        if total_words > MAX_WORDS_PER_SLIDE:
            raise ValueError(f"Slide {self.slide_number} exceeds {MAX_WORDS_PER_SLIDE} words.")
        return self


class SlideDeckPayload(BaseModel):
    """Strict slide deck payload produced by the LLM."""

    title: str = "Presentation"
    language: str | None = None
    slide_count: int
    slides: list[SlidePayload]

    @model_validator(mode="after")
    def validate_deck(self) -> "SlideDeckPayload":
        if not MIN_SLIDES <= len(self.slides) <= MAX_SLIDES:
            raise ValueError(f"Deck must contain {MIN_SLIDES}-{MAX_SLIDES} slides.")
        if self.slide_count != len(self.slides):
            raise ValueError("slide_count must match the number of slides.")
        if _normalized_label(self.slides[-1].title) in FINAL_SUMMARY_TITLES:
            raise ValueError("Do not create a final generic summary, recap, or conclusion slide.")

        previous_layout = ""
        repeat_count = 0
        bullet_like_streak = 0
        used_source_visuals: set[tuple[int | None, int | None]] = set()
        source_visual_count = 0
        for index, slide in enumerate(self.slides, 1):
            if slide.slide_number != index:
                raise ValueError("Slide numbers must be sequential starting at 1.")
            if slide.layout_type == previous_layout:
                repeat_count += 1
                if repeat_count > 2:
                    raise ValueError("Do not use the same layout more than two times consecutively.")
            else:
                previous_layout = slide.layout_type
                repeat_count = 1

            if slide.layout_type in BULLET_LIKE_LAYOUTS:
                bullet_like_streak += 1
                if bullet_like_streak > 2:
                    raise ValueError("Do not use bullet-like layouts more than two times consecutively.")
            else:
                bullet_like_streak = 0

            if slide.visual.kind != "none" and slide.layout_type not in VISUAL_LAYOUTS:
                raise ValueError("Visuals are only allowed on TITLE, FIGURE_FOCUS, or HIGHLIGHT_CARD slides.")
            if slide.visual.kind == "source_page":
                source_visual_count += 1
                visual_key = (slide.visual.source_index, slide.visual.page)
                if visual_key in used_source_visuals:
                    raise ValueError("Do not reuse the same source visual page across multiple slides.")
                used_source_visuals.add(visual_key)

        max_source_visuals = max(1, math.ceil(len(self.slides) * 0.35))
        if source_visual_count > max_source_visuals:
            raise ValueError("Too many source visuals; use them sparingly to avoid visual clutter.")
        return self


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_slide_deck_task(
    self,
    deck_id: str,
    notebook_id: str,
    user_id: str,
    document_names: list[str],
) -> dict[str, Any]:
    """Generate a grounded slide deck, render a raster PDF, and upload it."""
    settings = get_settings()
    client = get_supabase_client()
    repository = get_slide_deck_repository(client)
    document_repository = get_document_repository(client)
    if not repository.get(deck_id):
        logger.info("Slide deck task skipped because deck no longer exists deck_id=%s", deck_id)
        return _cancelled_result(deck_id, "missing")

    app_config = get_app_config()
    genai_client = genai.Client(api_key=settings.google_api_key)

    try:
        repository.update_status(deck_id, "processing", {"error_message": None})
    except ValueError as exc:
        if _is_missing_deck_error(exc):
            logger.info("Slide deck task skipped because deck no longer exists deck_id=%s", deck_id)
            return _cancelled_result(deck_id, "missing")
        raise

    uploaded_storage_path: str | None = None
    try:
        chunks = document_repository.get_all_chunks_by_names(document_names, notebook_id)
        if not chunks:
            raise ValueError("No indexed chunks were found for the selected documents.")

        context = _build_context(chunks)
        if len(context) > MAX_CONTEXT_CHARS:
            context = _summarize_context(genai_client, app_config.llm.gemini.model, context, document_names)

        visual_candidates = _visual_candidates(chunks)
        deck = _generate_deck(
            genai_client=genai_client,
            model=app_config.llm.gemini.model,
            context=context,
            document_names=document_names,
            visual_candidates=visual_candidates,
        )
        deck_json = _materialize_visuals(
            deck=deck.model_dump(),
            genai_client=genai_client,
            image_model=app_config.slide_deck.image_model,
            client=client,
            settings=settings,
            user_id=user_id,
            notebook_id=notebook_id,
            visual_candidates=visual_candidates,
        )
        deck_json["source_count"] = len(document_names)

        with tempfile.TemporaryDirectory(prefix="datn-slide-deck-") as temp_dir:
            workspace = Path(temp_dir)
            pdf_path = workspace / "presentation.pdf"
            _render_deck_pdf(deck_json, pdf_path)

            storage_path = f"{user_id}/{notebook_id}/{deck_id}.pdf"
            if not repository.get(deck_id):
                logger.info("Slide deck task cancelled before upload deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")

            _upload_pdf(client, settings.slide_deck_bucket, storage_path, pdf_path)
            uploaded_storage_path = storage_path

        metadata = {
            "document_names": document_names,
            "source_count": len(document_names),
            "task_id": self.request.id,
            "title": str(deck_json.get("title") or "Presentation"),
            "deck_json": deck_json,
            "content_type": "application/pdf",
            "error_message": None,
            "planner_model": app_config.llm.gemini.model,
            "image_model": app_config.slide_deck.image_model,
        }
        try:
            repository.update_status(deck_id, "completed", metadata, storage_path=storage_path)
        except ValueError as exc:
            if _is_missing_deck_error(exc):
                _remove_uploaded_pdf(client, settings.slide_deck_bucket, uploaded_storage_path)
                logger.info("Slide deck task finished after deck was deleted deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")
            raise

        return {
            "deck_id": deck_id,
            "status": "completed",
            "slide_count": len(deck_json.get("slides", [])),
            "storage_path": storage_path,
        }
    except Exception as exc:
        logger.exception("Slide deck generation failed deck_id=%s notebook_id=%s", deck_id, notebook_id)
        try:
            repository.update_status(
                deck_id,
                "failed",
                {
                    "document_names": document_names,
                    "source_count": len(document_names),
                    "task_id": self.request.id,
                    "error_message": str(exc),
                },
            )
        except ValueError as update_exc:
            if _is_missing_deck_error(update_exc):
                _remove_uploaded_pdf(client, settings.slide_deck_bucket, uploaded_storage_path)
                logger.info("Slide deck failure ignored because deck was deleted deck_id=%s", deck_id)
                return _cancelled_result(deck_id, "deleted")
            raise
        raise


def _build_context(chunks: list[dict[str, Any]]) -> str:
    """Format document chunks into compact source context."""
    parts: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        document = chunk.get("document_name", "unknown")
        page_range = chunk.get("page_range") or "unknown"
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        content = re.sub(r"\s+", " ", str(chunk.get("content", ""))).strip()
        if not content:
            continue
        visual_note = ""
        if metadata.get("has_visual"):
            visual_note = f"\nVisual candidate: yes; content_type={metadata.get('content_type', 'visual_description')}"
        parts.append(f"[Source {index}] Document: {document}; pages: {page_range}{visual_note}\n{content}")
    return "\n\n".join(parts)


def _summarize_context(genai_client: genai.Client, model: str, context: str, document_names: list[str]) -> str:
    """Summarize long notebook context in batches before final deck generation."""
    summaries: list[str] = []
    for batch in _split_text(context, BATCH_CONTEXT_CHARS):
        prompt = (
            "Summarize this document context for a concise academic presentation deck. "
            "Keep core claims, definitions, numbers, methods, comparisons, caveats, and relationships. "
            "Do not add facts that are not present. Do not write slide text yet.\n\n"
            f"Selected documents: {', '.join(document_names)}\n\n"
            f"Context:\n{batch}"
        )
        response = genai_client.models.generate_content(model=model, contents=prompt)
        summaries.append(str(response.text or "").strip())
    return "\n\n".join(summary for summary in summaries if summary)


def _generate_deck(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
) -> SlideDeckPayload:
    """Generate and validate a strict deck JSON payload."""
    retry_feedback = ""
    last_error: Exception | None = None

    for _attempt in range(MAX_DECK_ATTEMPTS):
        prompt = _deck_prompt(context, document_names, visual_candidates, retry_feedback)
        response = genai_client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.25,
                max_output_tokens=MAX_DECK_OUTPUT_TOKENS,
                response_mime_type="application/json",
                response_schema=SlideDeckPayload,
            ),
        )
        try:
            parsed_payload = _parsed_response_payload(response)
            if isinstance(parsed_payload, SlideDeckPayload):
                return parsed_payload
            return SlideDeckPayload.model_validate(parsed_payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            retry_feedback = (
                "\nYour previous JSON failed validation. Return a corrected JSON object only. "
                f"Validation error: {exc}\n"
            )

    raise ValueError(f"Gemini did not return a valid slide deck: {last_error}")


def _deck_prompt(context: str, document_names: list[str], visual_candidates: list[dict[str, Any]], retry_feedback: str) -> str:
    candidate_lines = []
    for candidate in visual_candidates[:12]:
        candidate_lines.append(
            f"- source_index={candidate['source_index']}; document={candidate['document_name']}; "
            f"pages={candidate['page_range']}; page={candidate.get('page') or 'unknown'}"
        )
    visual_text = "\n".join(candidate_lines) if candidate_lines else "- none"

    return f"""
You are creating a NotebookLM-style academic presentation.

Use only the supplied context. Auto-detect the main language from the context and write slide text in that language.

Goal:
- This is a presentation, not a document dump.
- Choose the smallest useful number of slides between {MIN_SLIDES} and {MAX_SLIDES}.
- Keep only core keywords, claims, methods, findings, comparisons, and implications.
- Prefer fewer slides and sharper wording over exhaustive coverage.

Allowed layout_type values:
- TITLE
- KEY_BULLETS
- TWO_COLUMNS
- THREE_FEATURES
- BIG_STAT
- FIGURE_FOCUS
- SECTION_DIVIDER
- HIGHLIGHT_CARD
- TIMELINE

Strict rules:
- Return only valid JSON.
- The JSON must match the response schema exactly; do not wrap it in markdown.
- Escape any quotation marks inside string values, or omit them.
- slide_count must equal the number of slides and must be between {MIN_SLIDES} and {MAX_SLIDES}.
- Each slide must be at most {MAX_WORDS_PER_SLIDE} visible words total.
- Each slide may have at most {MAX_BULLETS_PER_SLIDE} bullets.
- Each bullet must be at most {MAX_WORDS_PER_BULLET} words.
- Do not use the same layout_type more than 2 times consecutively.
- Do not use KEY_BULLETS more than 2 times consecutively.
- Use visual variety: prefer THREE_FEATURES, TWO_COLUMNS, BIG_STAT, HIGHLIGHT_CARD, TIMELINE, and SECTION_DIVIDER over plain bullets.
- If the context has distinct major topics, insert a SECTION_DIVIDER before switching topics.
- Do not create a final generic summary/recap/conclusion slide. Avoid slide titles like "Tóm tắt", "Summary", "Recap", or "Conclusion".
- Never reuse the same source visual/page on multiple slides.
- Use at most 1 source visual for every 3 slides; skip visuals that are dense, text-heavy, or only loosely related.
- Put visuals only on TITLE, FIGURE_FOCUS, or HIGHLIGHT_CARD slides.
- Do not include citation markers, source markers, footnotes, or bracket references like [1].
- If an idea is too long, shorten it or drop secondary details. Do not add slides just to carry more text.
- Use visual.kind "source_page" only when a supplied visual candidate clearly supports the slide.
- Use visual.kind "generated_image" only for a truly important hero/concept slide when no source visual fits.
- Otherwise use visual.kind "none".

Return this exact JSON shape:
{{
  "title": "Short presentation title",
  "language": "detected language name",
  "slide_count": 5,
  "slides": [
    {{
      "slide_number": 1,
      "layout_type": "TITLE",
      "title": "Short title",
      "subtitle": "Short subtitle",
      "bullets": [],
      "content": {{}},
      "visual": {{
        "kind": "none",
        "prompt": null,
        "source_index": null,
        "page": null,
        "alt": null
      }}
    }}
  ]
}}

For TWO_COLUMNS, content should use keys: left_title, right_title, left, right.
For THREE_FEATURES, content should use key features as a list of objects with title and text.
For BIG_STAT, content should use keys: stat, label, context.
For FIGURE_FOCUS, content should use keys: caption, takeaway.
For SECTION_DIVIDER, use title and subtitle only; bullets must be empty.
For HIGHLIGHT_CARD, content should use keys: label, context, takeaway.
For TIMELINE, content should use key steps as a list of 3-4 objects with title and text.

Selected documents: {", ".join(document_names)}

Available source visual candidates:
{visual_text}
{retry_feedback}
Context:
{context}
""".strip()


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
) -> dict[str, Any]:
    """Attach small preview image data URLs for selected visuals."""
    slides = deck.get("slides")
    if not isinstance(slides, list):
        return deck

    max_generated_images = 1 if len(slides) <= 5 else 2
    generated_count = 0
    candidates_by_source = {
        int(candidate["source_index"]): candidate for candidate in visual_candidates if "source_index" in candidate
    }

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        visual = slide.get("visual")
        if not isinstance(visual, dict):
            continue
        kind = visual.get("kind")
        if kind == "source_page":
            data_url = _source_visual_data_url(
                client=client,
                settings=settings,
                user_id=user_id,
                notebook_id=notebook_id,
                visual=visual,
                candidates_by_source=candidates_by_source,
            )
            if data_url:
                visual["data_url"] = data_url
            else:
                visual["kind"] = "none"
        elif kind == "generated_image":
            if generated_count >= max_generated_images:
                visual["kind"] = "none"
                continue
            prompt = str(visual.get("prompt") or "").strip()
            if not prompt:
                prompt = f"Minimal academic presentation visual for: {slide.get('title', 'key idea')}"
            data_url = _generate_image_data_url(genai_client, image_model, prompt)
            if data_url:
                visual["data_url"] = data_url
                generated_count += 1
            else:
                visual["kind"] = "none"

    deck["image_generation_count"] = generated_count
    return deck


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
    source_index = _int_or_none(visual.get("source_index"))
    candidate = candidates_by_source.get(source_index or -1)
    if not candidate:
        return None

    page = _int_or_none(visual.get("page")) or _int_or_none(candidate.get("page")) or 1
    document_name = str(candidate.get("document_name") or "").strip()
    storage_path = candidate.get("storage_path")
    possible_paths = [
        Path(settings.uploads_dir) / user_id / notebook_id / safe_pdf_storage_path(document_name),
    ]

    for local_path in possible_paths:
        if local_path.exists():
            return _render_pdf_page_data_url(local_path, page)

    storage_candidates = [storage_path] if isinstance(storage_path, str) and storage_path else []
    storage_candidates.append(f"{user_id}/{notebook_id}/{safe_pdf_storage_path(document_name)}")
    for path in dict.fromkeys(storage_candidates):
        with tempfile.TemporaryDirectory(prefix="datn-slide-source-") as temp_dir:
            local_path = Path(temp_dir) / "source.pdf"
            if _download_storage_object(client, "pdfs", path, local_path):
                return _render_pdf_page_data_url(local_path, page)
    return None


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


def _render_pdf_page_data_url(pdf_path: Path, page_number: int) -> str | None:
    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(pdf_path))
        page_index = max(page_number - 1, 0)
        if page_index >= len(pdf):
            page_index = 0
        page = pdf[page_index]
        bitmap = page.render(scale=2.4)
        image = bitmap.to_pil().convert("RGB")
        return _image_to_data_url(image)
    except Exception:
        logger.info("Could not render source PDF page for slide visual path=%s page=%s", pdf_path, page_number, exc_info=True)
        return None


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


def _render_deck_pdf(deck: dict[str, Any], pdf_path: Path) -> None:
    """Render deck JSON into a raster PDF."""
    slides = deck.get("slides") if isinstance(deck.get("slides"), list) else []
    if not slides:
        raise ValueError("Slide deck has no slides to render.")

    rendered = [_render_slide(deck, slide if isinstance(slide, dict) else {}) for slide in slides]
    first_image, *rest = rendered
    first_image.save(pdf_path, "PDF", resolution=288, save_all=True, append_images=rest)


def _render_slide(deck: dict[str, Any], slide: dict[str, Any]) -> Image.Image:
    image = Image.new("RGB", (SLIDE_WIDTH * PDF_RENDER_SCALE, SLIDE_HEIGHT * PDF_RENDER_SCALE), "#f7fafb")
    draw = _ScaledDraw(ImageDraw.Draw(image), PDF_RENDER_SCALE)
    title_font = _font(58, bold=True)
    subtitle_font = _font(34)
    heading_font = _font(34, bold=True)
    body_font = _font(28)
    small_font = _font(22)

    layout = str(slide.get("layout_type") or "KEY_BULLETS")
    title = str(slide.get("title") or deck.get("title") or "Presentation")
    subtitle = str(slide.get("subtitle") or "")

    _draw_top_rule(draw)
    _draw_slide_number(draw, slide.get("slide_number"), small_font)

    visual = slide.get("visual") if isinstance(slide.get("visual"), dict) else {}
    visual_image = _decode_data_url(str(visual.get("data_url") or ""))

    if layout == "TITLE":
        _draw_wrapped(draw, title, (150, 165), title_font, "#1f5666", max_width=1180, line_gap=10)
        if subtitle:
            _draw_wrapped(draw, subtitle, (155, 320), subtitle_font, "#2b3437", max_width=1120, line_gap=8)
        if visual_image:
            _paste_visual(image, visual_image, (360, 450, 1240, 720), rounded=False)
        else:
            _draw_waveform(draw, (315, 470, 1285, 730))
        return image

    if layout == "SECTION_DIVIDER":
        _render_section_divider(draw, title, subtitle, title_font, subtitle_font)
        return image

    _draw_wrapped(draw, title, (95, 75), heading_font, "#1f5666", max_width=980, line_gap=6)
    if subtitle:
        _draw_wrapped(draw, subtitle, (95, 132), small_font, "#586064", max_width=900, line_gap=4)

    if layout == "TWO_COLUMNS":
        _render_two_columns(draw, slide, body_font, small_font)
    elif layout == "THREE_FEATURES":
        _render_three_features(draw, slide, body_font, small_font)
    elif layout == "BIG_STAT":
        _render_big_stat(draw, slide, title_font, body_font, small_font)
    elif layout == "FIGURE_FOCUS":
        _render_figure_focus(image, draw, slide, visual_image, body_font, small_font)
    elif layout == "HIGHLIGHT_CARD":
        _render_highlight_card(image, draw, slide, visual_image, title_font, body_font, small_font)
    elif layout == "TIMELINE":
        _render_timeline(draw, slide, body_font, small_font)
    elif layout == "SUMMARY":
        _render_summary(draw, slide, body_font, small_font)
    else:
        _render_bullets(draw, slide, body_font)

    return image


class _ScaledDraw:
    """Draw in logical slide units while rendering to a high-resolution canvas."""

    def __init__(self, draw: ImageDraw.ImageDraw, scale: int):
        self._draw = draw
        self.scale = scale

    def rectangle(self, xy: Any, **kwargs: Any) -> None:
        self._draw.rectangle(self._scale_sequence(xy), **self._scale_kwargs(kwargs))

    def rounded_rectangle(self, xy: Any, **kwargs: Any) -> None:
        self._draw.rounded_rectangle(self._scale_sequence(xy), **self._scale_kwargs(kwargs))

    def text(self, xy: tuple[float, float], text: str, **kwargs: Any) -> None:
        self._draw.text(self._scale_point(xy), text, **kwargs)

    def ellipse(self, xy: Any, **kwargs: Any) -> None:
        self._draw.ellipse(self._scale_sequence(xy), **self._scale_kwargs(kwargs))

    def line(self, xy: Any, **kwargs: Any) -> None:
        self._draw.line(self._scale_sequence(xy), **self._scale_kwargs(kwargs))

    def textbbox(self, xy: tuple[float, float], text: str, **kwargs: Any) -> tuple[int, int, int, int]:
        bbox = self._draw.textbbox(self._scale_point(xy), text, **kwargs)
        return tuple(int(round(value / self.scale)) for value in bbox)

    def textlength(self, text: str, **kwargs: Any) -> float:
        return self._draw.textlength(text, **kwargs) / self.scale

    def _scale_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        scaled = dict(kwargs)
        for key in ("radius", "width"):
            if key in scaled and scaled[key] is not None:
                scaled[key] = max(1, int(round(float(scaled[key]) * self.scale)))
        return scaled

    def _scale_point(self, point: tuple[float, float]) -> tuple[int, int]:
        return (int(round(point[0] * self.scale)), int(round(point[1] * self.scale)))

    def _scale_sequence(self, value: Any) -> Any:
        if isinstance(value, list):
            return [self._scale_sequence(item) for item in value]
        if isinstance(value, tuple) and value and isinstance(value[0], (list, tuple)):
            return tuple(self._scale_sequence(item) for item in value)
        if isinstance(value, tuple):
            return tuple(int(round(float(item) * self.scale)) for item in value)
        return value


def _render_bullets(draw: ImageDraw.ImageDraw, slide: dict[str, Any], body_font: ImageFont.ImageFont) -> None:
    bullets = [str(item) for item in slide.get("bullets", []) if str(item).strip()]
    if not bullets:
        bullets = [text for text in _visible_strings(slide.get("content", {}))[:4]]
    y = 230
    for bullet in bullets[:4]:
        draw.ellipse((112, y + 12, 124, y + 24), fill="#d89c2b")
        y = _draw_wrapped(draw, bullet, (148, y), body_font, "#2b3437", max_width=790, line_gap=8) + 22


def _render_section_divider(
    draw: ImageDraw.ImageDraw,
    title: str,
    subtitle: str,
    title_font: ImageFont.ImageFont,
    subtitle_font: ImageFont.ImageFont,
) -> None:
    draw.rectangle((0, 0, SLIDE_WIDTH, SLIDE_HEIGHT), fill="#1f5666")
    draw.rectangle((0, 0, 42, SLIDE_HEIGHT), fill="#d89c2b")
    draw.line((150, 218, 420, 218), fill="#d89c2b", width=8)
    _draw_wrapped(draw, title, (150, 270), title_font, "#ffffff", max_width=1060, line_gap=12)
    if subtitle:
        _draw_wrapped(draw, subtitle, (154, 455), subtitle_font, "#dce9ed", max_width=980, line_gap=9)


def _render_summary(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    bullets = [str(item) for item in slide.get("bullets", []) if str(item).strip()]
    if not bullets:
        bullets = [text for text in _visible_strings(slide.get("content", {}))[:3]]
    boxes = [(120, 255, 500, 650), (610, 255, 990, 650), (1100, 255, 1480, 650)]
    for index, item in enumerate(bullets[:3]):
        box = boxes[index]
        x1, y1, _x2, _y2 = box
        draw.rounded_rectangle(box, radius=22, fill="#ffffff", outline="#d9e2e6", width=2)
        draw.ellipse((x1 + 34, y1 + 34, x1 + 82, y1 + 82), fill="#d89c2b")
        draw.text((x1 + 50, y1 + 43), str(index + 1), font=small_font, fill="#ffffff")
        _draw_wrapped(draw, item, (x1 + 36, y1 + 128), body_font, "#1f5666", max_width=300, line_gap=8)


def _render_two_columns(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    left = [str(item) for item in content.get("left", []) if str(item).strip()]
    right = [str(item) for item in content.get("right", []) if str(item).strip()]
    draw.rounded_rectangle((95, 210, 735, 695), radius=20, fill="#ffffff", outline="#d9e2e6")
    draw.rounded_rectangle((805, 210, 1445, 695), radius=20, fill="#ffffff", outline="#d9e2e6")
    draw.text((135, 245), str(content.get("left_title") or "Focus"), font=small_font, fill="#1f5666")
    draw.text((845, 245), str(content.get("right_title") or "Contrast"), font=small_font, fill="#1f5666")
    _draw_column_items(draw, left, (135, 305), body_font, 520)
    _draw_column_items(draw, right, (845, 305), body_font, 520)


def _render_three_features(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    boxes = [(95, 245, 485, 665), (605, 245, 995, 665), (1115, 245, 1505, 665)]
    for index, box in enumerate(boxes):
        feature = features[index] if index < len(features) and isinstance(features[index], dict) else {}
        draw.rounded_rectangle(box, radius=18, fill="#ffffff", outline="#d9e2e6")
        x1, y1, _x2, _y2 = box
        draw.text((x1 + 35, y1 + 35), f"0{index + 1}", font=small_font, fill="#d89c2b")
        _draw_wrapped(draw, str(feature.get("title") or ""), (x1 + 35, y1 + 92), body_font, "#1f5666", 305, 6)
        _draw_wrapped(draw, str(feature.get("text") or ""), (x1 + 35, y1 + 190), small_font, "#2b3437", 305, 6)


def _render_timeline(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    steps = content.get("steps") if isinstance(content.get("steps"), list) else []
    if not steps:
        steps = [{"title": f"Step {index + 1}", "text": text} for index, text in enumerate(_visible_strings(content)[:4])]
    steps = steps[:4]
    if not steps:
        return

    y_line = 430
    draw.line((165, y_line, 1435, y_line), fill="#c7d5da", width=5)
    slot_width = 1270 / max(len(steps) - 1, 1)
    for index, step in enumerate(steps):
        item = step if isinstance(step, dict) else {}
        x = int(165 + slot_width * index)
        draw.ellipse((x - 24, y_line - 24, x + 24, y_line + 24), fill="#1f5666")
        draw.text((x - 10, y_line - 15), str(index + 1), font=small_font, fill="#ffffff")
        text_x = max(95, min(x - 130, 1335))
        _draw_wrapped(draw, str(item.get("title") or ""), (text_x, y_line + 62), body_font, "#1f5666", 260, 6)
        _draw_wrapped(draw, str(item.get("text") or ""), (text_x, y_line + 140), small_font, "#2b3437", 260, 6)


def _render_big_stat(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    draw.rounded_rectangle((155, 250, 1445, 650), radius=24, fill="#ffffff", outline="#d9e2e6")
    stat = str(content.get("stat") or "")
    draw.text((215, 305), stat, font=_font(96, bold=True), fill="#1f5666")
    _draw_wrapped(draw, str(content.get("label") or ""), (220, 435), body_font, "#2b3437", 960, 8)
    _draw_wrapped(draw, str(content.get("context") or ""), (220, 530), small_font, "#586064", 980, 6)


def _render_figure_focus(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    visual_image: Image.Image | None,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    if visual_image:
        _paste_visual(image, visual_image, (95, 210, 920, 700))
    else:
        draw.rounded_rectangle((95, 210, 920, 700), radius=18, fill="#eaf0f3", outline="#d9e2e6")
        _draw_waveform(draw, (180, 365, 835, 545))
    _draw_wrapped(draw, str(content.get("caption") or ""), (995, 245), body_font, "#1f5666", 420, 8)
    _draw_wrapped(draw, str(content.get("takeaway") or ""), (995, 430), small_font, "#2b3437", 420, 7)


def _render_highlight_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    visual_image: Image.Image | None,
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    if visual_image:
        card = (95, 235, 910, 690)
        text_x = 985
        text_width = 420
        _paste_visual(image, visual_image, card)
    else:
        card = (140, 235, 1460, 680)
        text_x = 220
        text_width = 1060
        draw.rounded_rectangle(card, radius=26, fill="#ffffff", outline="#d9e2e6", width=2)

    label = str(content.get("label") or slide.get("title") or "")
    context = str(content.get("context") or "")
    takeaway = str(content.get("takeaway") or "")
    draw.text((text_x, 275), label, font=small_font, fill="#d89c2b")
    _draw_wrapped(draw, str(slide.get("title") or ""), (text_x, 330), title_font, "#1f5666", text_width, 10)
    if context:
        _draw_wrapped(draw, context, (text_x, 490), body_font, "#2b3437", text_width, 8)
    if takeaway:
        _draw_wrapped(draw, takeaway, (text_x, 615), small_font, "#586064", text_width, 7)


def _draw_column_items(
    draw: ImageDraw.ImageDraw,
    items: list[str],
    origin: tuple[int, int],
    font: ImageFont.ImageFont,
    max_width: int,
) -> None:
    x, y = origin
    for item in items[:4]:
        draw.ellipse((x, y + 13, x + 10, y + 23), fill="#d89c2b")
        y = _draw_wrapped(draw, item, (x + 28, y), font, "#2b3437", max_width, 7) + 20


def _draw_top_rule(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 0, SLIDE_WIDTH, 18), fill="#1f5666")
    draw.rectangle((0, 18, SLIDE_WIDTH, 25), fill="#d89c2b")


def _draw_slide_number(draw: ImageDraw.ImageDraw, number: Any, font: ImageFont.ImageFont) -> None:
    if number:
        draw.text((1500, 70), str(number), font=font, fill="#819097")


def _draw_waveform(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    mid = (y1 + y2) / 2
    width = x2 - x1
    points: list[tuple[float, float]] = []
    for i in range(80):
        x = x1 + width * i / 79
        amp = math.sin(i * 0.7) * 0.55 + math.sin(i * 0.19) * 0.35
        envelope = math.sin(math.pi * i / 79)
        y = mid + amp * envelope * (y2 - y1) * 0.38
        points.append((x, y))
    draw.line(points, fill="#1f5666", width=5)
    draw.line((x1, mid, x2, mid), fill="#c7d5da", width=2)


def _paste_visual(image: Image.Image, visual: Image.Image, box: tuple[int, int, int, int], rounded: bool = True) -> None:
    x1, y1, x2, y2 = _scaled_box(box)
    target_w = x2 - x1
    target_h = y2 - y1
    visual = visual.copy().convert("RGB")
    visual.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    paste_x = x1 + (target_w - visual.width) // 2
    paste_y = y1 + (target_h - visual.height) // 2
    image.paste(visual, (paste_x, paste_y))
    if rounded:
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=18 * PDF_RENDER_SCALE, outline="#d9e2e6", width=3 * PDF_RENDER_SCALE)


def _scaled_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return tuple(int(round(value * PDF_RENDER_SCALE)) for value in box)


def _decode_data_url(data_url: str) -> Image.Image | None:
    if not data_url.startswith("data:image/"):
        return None
    try:
        encoded = data_url.split(",", 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(encoded))).convert("RGB")
    except Exception:
        return None


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    scaled_size = max(1, int(round(size * PDF_RENDER_SCALE)))
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size=scaled_size)
    return ImageFont.load_default(size=scaled_size)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    origin: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int,
) -> int:
    x, y = origin
    lines = _wrap_text(draw, text, font, max_width)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _upload_pdf(client: Any, bucket: str, storage_path: str, pdf_path: Path) -> None:
    file_options = {"content-type": "application/pdf"}
    with pdf_path.open("rb") as file:
        try:
            client.storage.from_(bucket).update(storage_path, file, file_options=file_options)
        except Exception:
            file.seek(0)
            client.storage.from_(bucket).upload(storage_path, file, file_options=file_options)


def _remove_uploaded_pdf(client: Any, bucket: str, storage_path: str | None) -> None:
    if not storage_path:
        return
    try:
        client.storage.from_(bucket).remove([storage_path])
    except Exception:
        logger.info("Could not remove cancelled slide deck object path=%s.", storage_path, exc_info=True)


def _parse_json_object(value: str) -> dict[str, Any]:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from Gemini.")
    return parsed


def _parsed_response_payload(response: Any) -> dict[str, Any] | SlideDeckPayload:
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, SlideDeckPayload):
        return parsed
    if isinstance(parsed, BaseModel):
        return parsed.model_dump()
    if isinstance(parsed, dict):
        return parsed

    return _parse_json_object(str(getattr(response, "text", "") or ""))


def _visible_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        strings: list[str] = []
        for item in value:
            strings.extend(_visible_strings(item))
        return strings
    if isinstance(value, dict):
        strings = []
        for key, item in value.items():
            if key in {"visual", "data_url", "source_index", "page"}:
                continue
            strings.extend(_visible_strings(item))
        return strings
    return []


def _word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


def _normalized_label(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _first_page_from_range(value: Any) -> int | None:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_missing_deck_error(exc: Exception) -> bool:
    return isinstance(exc, ValueError) and str(exc) == "Slide deck not found."


def _cancelled_result(deck_id: str, reason: str) -> dict[str, Any]:
    return {
        "deck_id": deck_id,
        "status": "cancelled",
        "reason": reason,
    }


def _split_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
