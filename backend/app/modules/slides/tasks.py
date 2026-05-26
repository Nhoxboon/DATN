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
from app.modules.slides.browser_pdf_renderer import render_deck_pdf_with_browser
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
FLOW_ACTION_MAX_WORDS = 12
CARD_DESC_MAX_WORDS = 16
CALLOUT_MAX_WORDS = 24
LEGACY_LAYOUTS = {
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
COMPONENT_LAYOUTS = {
    "TITLE_HERO",
    "DUAL_PILLARS",
    "GRID_COMPOSITE",
    "PROCESS_FLOW_WITH_CALLOUT",
    "VISUAL_ANCHOR",
    "METRIC_DASHBOARD",
    "CODE_COMPARISON",
    "CHECKLIST",
    "TRANSITION",
}
VISUAL_LAYOUTS = {"TITLE_HERO", "VISUAL_ANCHOR"}
ICON_KEYS = {
    "cpu",
    "globe",
    "gauge",
    "database",
    "layers",
    "box",
    "route",
    "workflow",
    "warning",
    "check",
    "rocket",
    "zap",
    "code",
    "palette",
    "gamepad",
    "package",
    "server",
    "shield",
    "search",
    "list-checks",
    "repeat",
    "timer",
    "network",
}
ICON_LABELS = {
    "cpu": "CPU",
    "globe": "GLB",
    "gauge": "SPD",
    "database": "DB",
    "layers": "LYR",
    "box": "BOX",
    "route": "RTE",
    "workflow": "WF",
    "warning": "!",
    "check": "OK",
    "rocket": "GO",
    "zap": "ZAP",
    "code": "</>",
    "palette": "ART",
    "gamepad": "PAD",
    "package": "PKG",
    "server": "SRV",
    "shield": "SEC",
    "search": "SRC",
    "list-checks": "CHK",
    "repeat": "LOOP",
    "timer": "TIME",
    "network": "NET",
}
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
ALLOWED_LAYOUTS = COMPONENT_LAYOUTS
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
    """Short structured text item used by legacy and component layouts."""

    title: str | None = None
    text: str | None = None


class SlideCard(BaseModel):
    """Card component for grid and pillar slides."""

    id: str = ""
    tag: Literal["LEGACY", "MID_LEVEL", "RECOMMENDED", "WARNING", "INSIGHT", "DEFAULT"] = "DEFAULT"
    icon_key: Literal[
        "cpu",
        "globe",
        "gauge",
        "database",
        "layers",
        "box",
        "route",
        "workflow",
        "warning",
        "check",
        "rocket",
        "zap",
        "code",
        "palette",
        "gamepad",
        "package",
        "server",
        "shield",
        "search",
        "list-checks",
        "repeat",
        "timer",
        "network",
    ] = "check"
    heading: str = ""
    desc: str = ""

    @model_validator(mode="after")
    def validate_card_text(self) -> "SlideCard":
        if _word_count(self.heading) > 7:
            raise ValueError("Card heading must be a label, not a sentence.")
        if _word_count(self.desc) > CARD_DESC_MAX_WORDS:
            raise ValueError(f"Card desc must be at most {CARD_DESC_MAX_WORDS} words.")
        return self


class FlowStep(BaseModel):
    """Process step component with action language."""

    step: str = ""
    label: str = ""
    action: str = ""

    @model_validator(mode="after")
    def validate_flow_step(self) -> "FlowStep":
        if _word_count(self.label) > 5:
            raise ValueError("Flow step label must be at most 5 words.")
        if _word_count(self.action) > FLOW_ACTION_MAX_WORDS:
            raise ValueError(f"Flow step action must be at most {FLOW_ACTION_MAX_WORDS} words.")
        if self.action and not _looks_action_like(self.action):
            raise ValueError("Flow step action must be command-like, not descriptive prose.")
        return self


class CalloutBox(BaseModel):
    """Callout component for warnings and insights."""

    type: Literal["WARNING", "INSIGHT", "RECOMMENDED"] = "INSIGHT"
    text: str = ""

    @model_validator(mode="after")
    def validate_callout(self) -> "CalloutBox":
        if _word_count(self.text) > CALLOUT_MAX_WORDS:
            raise ValueError(f"Callout text must be at most {CALLOUT_MAX_WORDS} words.")
        return self


class MetricItem(BaseModel):
    """Metric component for dashboard slides."""

    icon_key: Literal[
        "cpu",
        "globe",
        "gauge",
        "database",
        "layers",
        "box",
        "route",
        "workflow",
        "warning",
        "check",
        "rocket",
        "zap",
        "code",
        "palette",
        "gamepad",
        "package",
        "server",
        "shield",
        "search",
        "list-checks",
        "repeat",
        "timer",
        "network",
    ] = "gauge"
    value: str = ""
    label: str = ""
    context: str = ""


class ComparisonItem(BaseModel):
    """Comparison row for code and before/after layouts."""

    label: str = ""
    left: str = ""
    right: str = ""


class ChecklistItem(BaseModel):
    """Checklist row."""

    text: str = ""
    icon_key: Literal[
        "cpu",
        "globe",
        "gauge",
        "database",
        "layers",
        "box",
        "route",
        "workflow",
        "warning",
        "check",
        "rocket",
        "zap",
        "code",
        "palette",
        "gamepad",
        "package",
        "server",
        "shield",
        "search",
        "list-checks",
        "repeat",
        "timer",
        "network",
    ] = "check"


class VisualAnchor(BaseModel):
    """Primary visual anchor for a slide."""

    kind: Literal["none", "icon", "source_page", "generated_image"] = "none"
    icon_key: Literal[
        "cpu",
        "globe",
        "gauge",
        "database",
        "layers",
        "box",
        "route",
        "workflow",
        "warning",
        "check",
        "rocket",
        "zap",
        "code",
        "palette",
        "gamepad",
        "package",
        "server",
        "shield",
        "search",
        "list-checks",
        "repeat",
        "timer",
        "network",
    ] | None = None
    caption: str | None = None
    prompt: str | None = None
    source_index: int | None = None
    page: int | None = None
    alt: str | None = None
    data_url: str | None = None


class SlideComponents(BaseModel):
    """High-level slide components used by the V2 layout agent."""

    cards: list[SlideCard] = Field(default_factory=list)
    flow_steps: list[FlowStep] = Field(default_factory=list)
    callout_box: CalloutBox | None = None
    metrics: list[MetricItem] = Field(default_factory=list)
    comparison: list[ComparisonItem] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    visual_anchor: VisualAnchor = Field(default_factory=VisualAnchor)


class SlideContent(BaseModel):
    """Legacy layout-specific content kept so old saved decks still render."""

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
        "TITLE_HERO",
        "DUAL_PILLARS",
        "GRID_COMPOSITE",
        "PROCESS_FLOW_WITH_CALLOUT",
        "VISUAL_ANCHOR",
        "METRIC_DASHBOARD",
        "CODE_COMPARISON",
        "CHECKLIST",
        "TRANSITION",
    ]
    title: str = ""
    subtitle: str | None = None
    bullets: list[str] = Field(default_factory=list)
    components: SlideComponents = Field(default_factory=SlideComponents)
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
                "components": self.components.model_dump(),
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

            _validate_components_for_layout(slide)

            visual_anchor = slide.components.visual_anchor
            has_image_visual = visual_anchor.kind in {"source_page", "generated_image"} or slide.visual.kind in {
                "source_page",
                "generated_image",
            }
            if has_image_visual and slide.layout_type not in VISUAL_LAYOUTS:
                raise ValueError("Image visuals are only allowed on TITLE_HERO or VISUAL_ANCHOR slides.")
            if visual_anchor.kind == "source_page":
                source_visual_count += 1
                visual_key = (visual_anchor.source_index, visual_anchor.page)
                if visual_key in used_source_visuals:
                    raise ValueError("Do not reuse the same source visual page across multiple slides.")
                used_source_visuals.add(visual_key)

        max_source_visuals = max(1, math.ceil(len(self.slides) * 0.35))
        if source_visual_count > max_source_visuals:
            raise ValueError("Too many source visuals; use them sparingly to avoid visual clutter.")
        review_issues = _review_deck_design(self)
        if review_issues:
            raise ValueError("; ".join(review_issues))
        return self


class OutlineSlide(BaseModel):
    """One planned slide before detailed composition."""

    slide_number: int
    chapter: str = ""
    layout_type: Literal[
        "TITLE_HERO",
        "DUAL_PILLARS",
        "GRID_COMPOSITE",
        "PROCESS_FLOW_WITH_CALLOUT",
        "VISUAL_ANCHOR",
        "METRIC_DASHBOARD",
        "CODE_COMPARISON",
        "CHECKLIST",
        "TRANSITION",
    ]
    title: str = ""
    purpose: str = ""
    visual_strategy: Literal["icon", "source_page", "generated_image", "none"] = "icon"


class StoryOutlinePayload(BaseModel):
    """Planner output that fixes the narrative before slide writing."""

    title: str = "Presentation"
    language: str | None = None
    slide_count: int
    chapters: list[str] = Field(default_factory=list)
    slides: list[OutlineSlide]

    @model_validator(mode="after")
    def validate_outline(self) -> "StoryOutlinePayload":
        if not MIN_SLIDES <= len(self.slides) <= MAX_SLIDES:
            raise ValueError(f"Outline must contain {MIN_SLIDES}-{MAX_SLIDES} slides.")
        if self.slide_count != len(self.slides):
            raise ValueError("slide_count must match outline slides.")
        chapters = {_normalized_label(slide.chapter) for slide in self.slides if slide.chapter}
        has_topic_switch = len(chapters) >= 2
        has_transition = any(slide.layout_type == "TRANSITION" for slide in self.slides)
        if has_topic_switch and not has_transition:
            raise ValueError("Outline must include a TRANSITION slide when it has two or more major chapters.")
        for index, slide in enumerate(self.slides, 1):
            if slide.slide_number != index:
                raise ValueError("Outline slide numbers must be sequential.")
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
        deck, outline = _generate_deck(
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
        deck_json["story_outline"] = outline.model_dump()
        deck_json["source_count"] = len(document_names)

        with tempfile.TemporaryDirectory(prefix="datn-slide-deck-") as temp_dir:
            workspace = Path(temp_dir)
            pdf_path = workspace / "presentation.pdf"
            pdf_renderer = _render_deck_pdf_for_config(deck_json, pdf_path, app_config.slide_deck)

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
            "pdf_renderer": pdf_renderer,
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
            "pdf_renderer": pdf_renderer,
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
) -> tuple[SlideDeckPayload, StoryOutlinePayload]:
    """Plan a story outline, compose slides, then repair design issues."""
    outline = _generate_story_outline(
        genai_client=genai_client,
        model=model,
        context=context,
        document_names=document_names,
        visual_candidates=visual_candidates,
    )
    deck = _compose_deck(
        genai_client=genai_client,
        model=model,
        context=context,
        document_names=document_names,
        visual_candidates=visual_candidates,
        outline=outline,
    )
    return deck, outline


def _generate_story_outline(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
) -> StoryOutlinePayload:
    """Generate the deck narrative before slide composition."""
    retry_feedback = ""
    last_error: Exception | None = None

    for _attempt in range(MAX_DECK_ATTEMPTS):
        response = genai_client.models.generate_content(
            model=model,
            contents=_outline_prompt(context, document_names, visual_candidates, retry_feedback),
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=5000,
                response_mime_type="application/json",
                response_schema=StoryOutlinePayload,
            ),
        )
        try:
            parsed_payload = _parsed_response_payload(response)
            if isinstance(parsed_payload, StoryOutlinePayload):
                return parsed_payload
            return StoryOutlinePayload.model_validate(parsed_payload)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            retry_feedback = (
                "\nYour previous outline failed validation. Return corrected JSON only. "
                f"Validation error: {exc}\n"
            )

    raise ValueError(f"Gemini did not return a valid slide outline: {last_error}")


def _compose_deck(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    outline: StoryOutlinePayload,
) -> SlideDeckPayload:
    """Generate and validate a strict deck JSON payload."""
    retry_feedback = ""
    last_error: Exception | None = None

    for _attempt in range(MAX_DECK_ATTEMPTS):
        prompt = _deck_prompt(context, document_names, visual_candidates, outline, retry_feedback)
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
                deck = parsed_payload
            else:
                parsed_payload = _repair_deck_payload(parsed_payload)
                deck = SlideDeckPayload.model_validate(parsed_payload)
            review_issues = _review_deck_design(deck)
            if review_issues:
                raise ValueError("; ".join(review_issues))
            return deck
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            retry_feedback = (
                "\nYour previous JSON failed validation. Return a corrected JSON object only. "
                f"Validation error: {exc}\n"
            )

    raise ValueError(f"Gemini did not return a valid slide deck: {last_error}")


def _outline_prompt(
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    retry_feedback: str,
) -> str:
    visual_text = _visual_candidates_text(visual_candidates)

    return f"""
You are the Story Outline Planner for a NotebookLM-quality academic presentation.

Use only the supplied context. Auto-detect the main language and write in that language.

Planning goals:
- Choose {MIN_SLIDES}-{MAX_SLIDES} slides.
- Build a clear story with chapters, not a list of extracted headings.
- If there are two or more major topics, add exactly one TRANSITION slide at the chapter boundary.
- Prefer 8-12 slides when the source has multiple technical sections; do not compress unrelated chapters into one slide.
- Assign each slide one visual strategy: icon, source_page, generated_image, or none.
- Do not plan a final generic summary/recap/conclusion slide.

Allowed layout_type values:
- TITLE_HERO
- DUAL_PILLARS
- GRID_COMPOSITE
- PROCESS_FLOW_WITH_CALLOUT
- VISUAL_ANCHOR
- METRIC_DASHBOARD
- CODE_COMPARISON
- CHECKLIST
- TRANSITION

Return only valid JSON matching the response schema.

Selected documents: {", ".join(document_names)}

Available source visual candidates:
{visual_text}
{retry_feedback}
Context:
{context}
""".strip()


def _deck_prompt(
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    outline: StoryOutlinePayload,
    retry_feedback: str,
) -> str:
    visual_text = _visual_candidates_text(visual_candidates)
    outline_json = json.dumps(outline.model_dump(), ensure_ascii=False, indent=2)
    icon_keys = ", ".join(sorted(ICON_KEYS))

    return f"""
You are the Slide Composer and Design Reviewer for a NotebookLM-style academic presentation.

Use the approved story outline exactly. Use only the supplied context. Write slide text in the detected language.

Design goals:
- Convert evidence into visual components, not prose boxes.
- Every technical concept should be expressed as Action, Technique, Metric, Comparison, or Callout.
- Use visual anchors: icon_key on cards/metrics/checklists, source_page only when clearly useful, generated_image only for a hero/concept slide.
- source_page and generated_image are allowed only on TITLE_HERO or VISUAL_ANCHOR slides; every other layout must set visual.kind="none" and components.visual_anchor.kind="none" unless it uses card/metric/checklist icons.
- Do not write generic summary, recap, or conclusion slides.
- Do not use citations, source markers, or bracket references.

Allowed layout_type values:
- TITLE_HERO
- DUAL_PILLARS
- GRID_COMPOSITE
- PROCESS_FLOW_WITH_CALLOUT
- VISUAL_ANCHOR
- METRIC_DASHBOARD
- CODE_COMPARISON
- CHECKLIST
- TRANSITION

Component rules:
- GRID_COMPOSITE: 3 cards with id, tag, icon_key, heading, desc.
- DUAL_PILLARS: 2 cards; each card must have icon_key, heading, desc.
- PROCESS_FLOW_WITH_CALLOUT: 3-5 flow_steps and one callout_box.
- VISUAL_ANCHOR: components.visual_anchor must be icon, source_page, or generated_image and include a short caption.
- METRIC_DASHBOARD: 3-5 metrics with icon_key, value, label, context.
- CODE_COMPARISON: 2-4 comparison rows with label, left, right.
- CHECKLIST: 4-5 checklist items with icon_key and command-like text.
- TRANSITION: title and subtitle only; keep components empty.

Text constraints:
- Card desc <= {CARD_DESC_MAX_WORDS} words.
- Flow step action <= {FLOW_ACTION_MAX_WORDS} words and must sound command-like.
- Callout text <= {CALLOUT_MAX_WORDS} words.
- Vietnamese flow actions should start with imperative verbs like "Cập nhật", "Thiết lập", "Tải", "Nạp", "Hiển thị", "Kiểm tra", "Tách", or "Tối ưu".
- Each slide <= {MAX_WORDS_PER_SLIDE} visible words.
- Avoid full sentences where a label or command works.

Icon allowlist:
{icon_keys}

Approved story outline:
{outline_json}

Return this exact JSON shape:
{{
  "title": "Short presentation title",
  "language": "detected language name",
  "slide_count": {outline.slide_count},
  "slides": [
    {{
      "slide_number": 1,
      "layout_type": "TITLE_HERO",
      "title": "Short title",
      "subtitle": "Short subtitle",
      "bullets": [],
      "components": {{
        "cards": [],
        "flow_steps": [],
        "callout_box": null,
        "metrics": [],
        "comparison": [],
        "checklist": [],
        "visual_anchor": {{
          "kind": "icon",
          "icon_key": "rocket",
          "caption": "Short caption",
          "prompt": null,
          "source_index": null,
          "page": null,
          "alt": null
        }}
      }},
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

For source_page or generated_image visual anchors, set both components.visual_anchor and visual with the same kind/source/prompt.

Selected documents: {", ".join(document_names)}

Available source visual candidates:
{visual_text}
{retry_feedback}
Context:
{context}
""".strip()


def _visual_candidates_text(visual_candidates: list[dict[str, Any]]) -> str:
    candidate_lines = []
    for candidate in visual_candidates[:12]:
        candidate_lines.append(
            f"- source_index={candidate['source_index']}; document={candidate['document_name']}; "
            f"pages={candidate['page_range']}; page={candidate.get('page') or 'unknown'}"
        )
    return "\n".join(candidate_lines) if candidate_lines else "- none"


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
            visual = {}
            slide["visual"] = visual
        anchor = _slide_visual_anchor(slide)
        kind = anchor.get("kind") or visual.get("kind")
        layout = str(slide.get("layout_type") or "")
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
            data_url = _source_visual_data_url(
                client=client,
                settings=settings,
                user_id=user_id,
                notebook_id=notebook_id,
                visual=visual if visual.get("source_index") else anchor,
                candidates_by_source=candidates_by_source,
            )
            if data_url:
                visual["data_url"] = data_url
                anchor["data_url"] = data_url
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
    return deck


def _slide_visual_anchor(slide: dict[str, Any]) -> dict[str, Any]:
    components = slide.get("components") if isinstance(slide.get("components"), dict) else {}
    anchor = components.get("visual_anchor") if isinstance(components.get("visual_anchor"), dict) else None
    if anchor is None:
        anchor = {}
        components["visual_anchor"] = anchor
        slide["components"] = components
    return anchor


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


def _render_deck_pdf_for_config(deck: dict[str, Any], pdf_path: Path, slide_config: Any) -> str:
    """Render a deck PDF using the configured renderer, with Pillow fallback."""
    renderer = str(getattr(slide_config, "pdf_renderer", "pillow") or "pillow").casefold()
    fallback = str(getattr(slide_config, "pdf_renderer_fallback", "pillow") or "none").casefold()
    timeout_seconds = int(getattr(slide_config, "browser_render_timeout_seconds", 30) or 30)
    max_retries = max(0, int(getattr(slide_config, "browser_max_retries", 0) or 0))
    screenshot_scale = float(getattr(slide_config, "browser_screenshot_scale", PDF_RENDER_SCALE) or PDF_RENDER_SCALE)

    if renderer != "browser":
        _render_deck_pdf(deck, pdf_path)
        return "pillow"

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            render_deck_pdf_with_browser(
                deck,
                pdf_path,
                timeout_seconds=timeout_seconds,
                screenshot_scale=screenshot_scale,
            )
            return "browser"
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Browser slide PDF render failed attempt=%s/%s error=%s",
                attempt + 1,
                max_retries + 1,
                exc,
                exc_info=True,
            )

    if fallback == "pillow":
        _render_deck_pdf(deck, pdf_path)
        return "pillow_fallback"

    raise RuntimeError("Browser slide PDF render failed and fallback is disabled.") from last_error


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
    components = slide.get("components") if isinstance(slide.get("components"), dict) else {}
    anchor = components.get("visual_anchor") if isinstance(components.get("visual_anchor"), dict) else {}
    if not visual_image and isinstance(anchor, dict):
        visual_image = _decode_data_url(str(anchor.get("data_url") or ""))

    if layout == "TITLE_HERO":
        _render_title_hero(image, draw, slide, visual_image, title_font, subtitle_font, body_font)
        return image

    if layout == "TRANSITION":
        _render_section_divider(draw, title, subtitle, title_font, subtitle_font)
        return image

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

    if layout == "DUAL_PILLARS":
        _render_dual_pillars(draw, slide, body_font, small_font)
    elif layout == "GRID_COMPOSITE":
        _render_grid_composite(draw, slide, body_font, small_font)
    elif layout == "PROCESS_FLOW_WITH_CALLOUT":
        _render_process_flow_with_callout(draw, slide, body_font, small_font)
    elif layout == "VISUAL_ANCHOR":
        _render_visual_anchor(image, draw, slide, visual_image, title_font, body_font, small_font)
    elif layout == "METRIC_DASHBOARD":
        _render_metric_dashboard(draw, slide, title_font, body_font, small_font)
    elif layout == "CODE_COMPARISON":
        _render_code_comparison(draw, slide, body_font, small_font)
    elif layout == "CHECKLIST":
        _render_checklist(draw, slide, body_font, small_font)
    elif layout == "TWO_COLUMNS":
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


def _render_title_hero(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    visual_image: Image.Image | None,
    title_font: ImageFont.ImageFont,
    subtitle_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
) -> None:
    title = str(slide.get("title") or "Presentation")
    subtitle = str(slide.get("subtitle") or "")
    anchor = _component_anchor(slide)
    _draw_wrapped(draw, title, (120, 155), title_font, "#1f5666", max_width=980, line_gap=10)
    if subtitle:
        _draw_wrapped(draw, subtitle, (125, 325), subtitle_font, "#2b3437", max_width=900, line_gap=8)
    if visual_image:
        _paste_visual(image, visual_image, (1050, 180, 1485, 685), rounded=True)
    else:
        _draw_large_icon_anchor(draw, str(anchor.get("icon_key") or "rocket"), (1080, 230, 1450, 600), body_font)
    caption = str(anchor.get("caption") or "")
    if caption:
        _draw_wrapped(draw, caption, (1085, 635), body_font, "#586064", max_width=380, line_gap=6)


def _render_dual_pillars(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    cards = _component_cards(slide)[:2]
    boxes = [(120, 215, 745, 690), (855, 215, 1480, 690)]
    for index, box in enumerate(boxes):
        card = cards[index] if index < len(cards) else {}
        _draw_component_card(draw, card, box, body_font, small_font)


def _render_grid_composite(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    cards = _component_cards(slide)[:3]
    boxes = [(95, 235, 495, 680), (600, 235, 1000, 680), (1105, 235, 1505, 680)]
    for index, box in enumerate(boxes):
        card = cards[index] if index < len(cards) else {}
        _draw_component_card(draw, card, box, body_font, small_font)


def _render_process_flow_with_callout(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    steps = _component_flow_steps(slide)[:5]
    if not steps:
        return
    x_start = 95
    y = 300
    step_width = 270
    gap = 22
    for index, step in enumerate(steps):
        x = x_start + index * (step_width + gap)
        box = (x, y, x + step_width, y + 220)
        draw.rounded_rectangle(box, radius=18, fill="#ffffff", outline="#c7d5da", width=2)
        draw.text((x + 22, y + 24), str(step.get("step") or index + 1), font=small_font, fill="#d89c2b")
        _draw_wrapped(draw, str(step.get("label") or ""), (x + 22, y + 68), body_font, "#1f5666", max_width=220, line_gap=6)
        _draw_wrapped(draw, str(step.get("action") or ""), (x + 22, y + 145), small_font, "#2b3437", max_width=220, line_gap=5)
        if index < len(steps) - 1:
            draw.line((x + step_width + 4, y + 108, x + step_width + gap - 4, y + 108), fill="#1f5666", width=4)
    callout = _component_callout(slide)
    if callout:
        _draw_callout(draw, callout, (180, 610, 1420, 760), body_font, small_font)


def _render_visual_anchor(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    visual_image: Image.Image | None,
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    anchor = _component_anchor(slide)
    if visual_image:
        _paste_visual(image, visual_image, (95, 210, 920, 700), rounded=True)
    else:
        _draw_large_icon_anchor(draw, str(anchor.get("icon_key") or "workflow"), (170, 250, 850, 660), body_font)
    caption = str(anchor.get("caption") or "")
    _draw_wrapped(draw, str(slide.get("title") or ""), (995, 245), title_font, "#1f5666", 420, 8)
    if caption:
        _draw_wrapped(draw, caption, (1000, 460), body_font, "#2b3437", 410, 8)
    callout = _component_callout(slide)
    if callout:
        _draw_callout(draw, callout, (990, 610, 1485, 745), small_font, small_font)


def _render_metric_dashboard(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    title_font: ImageFont.ImageFont,
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    metrics = _component_metrics(slide)[:5]
    boxes = [(95, 235, 555, 430), (615, 235, 1075, 430), (1135, 235, 1505, 430), (215, 500, 735, 705), (865, 500, 1385, 705)]
    for index, metric in enumerate(metrics):
        box = boxes[index]
        x1, y1, _x2, _y2 = box
        draw.rounded_rectangle(box, radius=20, fill="#ffffff", outline="#d9e2e6", width=2)
        _draw_icon_badge(draw, str(metric.get("icon_key") or "gauge"), (x1 + 26, y1 + 28), small_font)
        draw.text((x1 + 102, y1 + 32), str(metric.get("value") or ""), font=title_font, fill="#1f5666")
        _draw_wrapped(draw, str(metric.get("label") or ""), (x1 + 32, y1 + 105), body_font, "#2b3437", 360, 6)
        _draw_wrapped(draw, str(metric.get("context") or ""), (x1 + 32, y1 + 152), small_font, "#586064", 360, 5)


def _render_code_comparison(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    rows = _component_comparison(slide)[:4]
    draw.rounded_rectangle((95, 215, 735, 715), radius=18, fill="#202529", outline="#202529", width=2)
    draw.rounded_rectangle((865, 215, 1505, 715), radius=18, fill="#ffffff", outline="#c7d5da", width=2)
    draw.text((135, 250), "Before", font=small_font, fill="#d89c2b")
    draw.text((905, 250), "After", font=small_font, fill="#1f5666")
    y = 310
    for row in rows:
        label = str(row.get("label") or "")
        if label:
            draw.text((135, y), label, font=small_font, fill="#819097")
            draw.text((905, y), label, font=small_font, fill="#819097")
            y += 34
        _draw_wrapped(draw, str(row.get("left") or ""), (135, y), body_font, "#ffffff", 520, 8)
        _draw_wrapped(draw, str(row.get("right") or ""), (905, y), body_font, "#2b3437", 520, 8)
        y += 86


def _render_checklist(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    items = _component_checklist(slide)[:5]
    y = 225
    for item in items:
        draw.rounded_rectangle((150, y, 1450, y + 88), radius=16, fill="#ffffff", outline="#d9e2e6", width=2)
        _draw_icon_badge(draw, str(item.get("icon_key") or "check"), (185, y + 22), small_font, fill="#16a34a")
        _draw_wrapped(draw, str(item.get("text") or ""), (260, y + 26), body_font, "#2b3437", 1080, 6)
        y += 105


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


def _draw_component_card(
    draw: ImageDraw.ImageDraw,
    card: dict[str, Any],
    box: tuple[int, int, int, int],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    tag = str(card.get("tag") or "DEFAULT")
    fill, outline, accent = _tag_style(tag)
    x1, y1, x2, _y2 = box
    draw.rounded_rectangle(box, radius=20, fill=fill, outline=outline, width=3)
    _draw_icon_badge(draw, str(card.get("icon_key") or "check"), (x1 + 34, y1 + 36), small_font, fill=accent)
    draw.text((x1 + 110, y1 + 42), tag.replace("_", " "), font=small_font, fill=accent)
    _draw_wrapped(draw, str(card.get("heading") or ""), (x1 + 36, y1 + 125), body_font, "#1f5666", x2 - x1 - 72, 8)
    _draw_wrapped(draw, str(card.get("desc") or ""), (x1 + 36, y1 + 235), small_font, "#2b3437", x2 - x1 - 72, 7)


def _draw_callout(
    draw: ImageDraw.ImageDraw,
    callout: dict[str, Any],
    box: tuple[int, int, int, int],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    callout_type = str(callout.get("type") or "INSIGHT")
    if callout_type == "WARNING":
        fill, outline, text_fill, icon = "#2b250f", "#d89c2b", "#fff4cf", "warning"
    elif callout_type == "RECOMMENDED":
        fill, outline, text_fill, icon = "#ecfdf5", "#10b981", "#065f46", "check"
    else:
        fill, outline, text_fill, icon = "#eef9fb", "#1f9eb3", "#1f5666", "zap"
    x1, y1, x2, _y2 = box
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=3)
    _draw_icon_badge(draw, icon, (x1 + 32, y1 + 34), small_font, fill=outline)
    draw.text((x1 + 105, y1 + 28), callout_type, font=small_font, fill=outline)
    _draw_wrapped(draw, str(callout.get("text") or ""), (x1 + 105, y1 + 70), body_font, text_fill, x2 - x1 - 145, 7)


def _draw_icon_badge(
    draw: ImageDraw.ImageDraw,
    icon_key: str,
    origin: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str = "#1f5666",
) -> None:
    x, y = origin
    draw.ellipse((x, y, x + 52, y + 52), fill=fill)
    label = ICON_LABELS.get(icon_key, icon_key[:3].upper())
    draw.text((x + 11, y + 16), label[:4], font=font, fill="#ffffff")


def _draw_large_icon_anchor(
    draw: ImageDraw.ImageDraw,
    icon_key: str,
    box: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=32, fill="#ffffff", outline="#d9e2e6", width=3)
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    draw.ellipse((cx - 100, cy - 100, cx + 100, cy + 100), fill="#1f5666")
    label = ICON_LABELS.get(icon_key, icon_key[:3].upper())
    draw.text((cx - 45, cy - 20), label[:4], font=font, fill="#ffffff")


def _tag_style(tag: str) -> tuple[str, str, str]:
    if tag == "RECOMMENDED":
        return "#ecfdf5", "#10b981", "#059669"
    if tag == "WARNING":
        return "#fff7ed", "#f59e0b", "#d97706"
    if tag == "INSIGHT":
        return "#eef9fb", "#1f9eb3", "#1f5666"
    if tag == "LEGACY":
        return "#f8fafc", "#94a3b8", "#64748b"
    if tag == "MID_LEVEL":
        return "#f5f3ff", "#8b5cf6", "#7c3aed"
    return "#ffffff", "#d9e2e6", "#1f5666"


def _component_dict(slide: dict[str, Any]) -> dict[str, Any]:
    return slide.get("components") if isinstance(slide.get("components"), dict) else {}


def _component_cards(slide: dict[str, Any]) -> list[dict[str, Any]]:
    value = _component_dict(slide).get("cards")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _component_flow_steps(slide: dict[str, Any]) -> list[dict[str, Any]]:
    value = _component_dict(slide).get("flow_steps")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _component_metrics(slide: dict[str, Any]) -> list[dict[str, Any]]:
    value = _component_dict(slide).get("metrics")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _component_comparison(slide: dict[str, Any]) -> list[dict[str, Any]]:
    value = _component_dict(slide).get("comparison")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _component_checklist(slide: dict[str, Any]) -> list[dict[str, Any]]:
    value = _component_dict(slide).get("checklist")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _component_callout(slide: dict[str, Any]) -> dict[str, Any] | None:
    value = _component_dict(slide).get("callout_box")
    return value if isinstance(value, dict) else None


def _component_anchor(slide: dict[str, Any]) -> dict[str, Any]:
    value = _component_dict(slide).get("visual_anchor")
    return value if isinstance(value, dict) else {}


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


def _repair_deck_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize small text overruns before strict validation."""
    repaired = dict(payload)
    slides = repaired.get("slides")
    if not isinstance(slides, list):
        return repaired

    repaired_slides: list[Any] = []
    for slide in slides:
        if not isinstance(slide, dict):
            repaired_slides.append(slide)
            continue
        fixed_slide = dict(slide)
        fixed_slide["title"] = _truncate_words(str(fixed_slide.get("title") or ""), 10)
        if fixed_slide.get("subtitle"):
            fixed_slide["subtitle"] = _truncate_words(str(fixed_slide.get("subtitle") or ""), 18)
        if fixed_slide.get("layout_type") in COMPONENT_LAYOUTS:
            fixed_slide["bullets"] = []
            fixed_slide["content"] = {}

        components = fixed_slide.get("components") if isinstance(fixed_slide.get("components"), dict) else {}
        fixed_components = dict(components)

        fixed_components["cards"] = [
            _repair_card_payload(card)
            for card in fixed_components.get("cards", [])
            if isinstance(card, dict)
        ]
        fixed_components["flow_steps"] = [
            _repair_flow_step_payload(step)
            for step in fixed_components.get("flow_steps", [])
            if isinstance(step, dict)
        ]
        callout = fixed_components.get("callout_box")
        if isinstance(callout, dict):
            fixed_components["callout_box"] = {
                **callout,
                "text": _truncate_words(str(callout.get("text") or ""), CALLOUT_MAX_WORDS),
            }
        fixed_components["metrics"] = [
            _repair_metric_payload(metric)
            for metric in fixed_components.get("metrics", [])
            if isinstance(metric, dict)
        ]
        fixed_components["comparison"] = [
            _repair_comparison_payload(row)
            for row in fixed_components.get("comparison", [])
            if isinstance(row, dict)
        ]
        fixed_components["checklist"] = [
            _repair_checklist_payload(item)
            for item in fixed_components.get("checklist", [])
            if isinstance(item, dict)
        ]
        anchor = fixed_components.get("visual_anchor")
        if isinstance(anchor, dict) and anchor.get("caption"):
            fixed_components["visual_anchor"] = {
                **anchor,
                "caption": _truncate_words(str(anchor.get("caption") or ""), 14),
            }
        fixed_slide["components"] = fixed_components
        fixed_slide = _repair_visual_placement(fixed_slide)
        fixed_slide = _fit_slide_to_word_budget(fixed_slide)
        repaired_slides.append(fixed_slide)

    repaired["slides"] = repaired_slides
    return repaired


def _repair_visual_placement(slide: dict[str, Any]) -> dict[str, Any]:
    """Keep expensive image visuals only on layouts that actually render them."""
    layout = str(slide.get("layout_type") or "")
    fixed = dict(slide)
    visual = fixed.get("visual") if isinstance(fixed.get("visual"), dict) else {}
    components = fixed.get("components") if isinstance(fixed.get("components"), dict) else {}
    anchor = components.get("visual_anchor") if isinstance(components.get("visual_anchor"), dict) else {}

    if layout not in VISUAL_LAYOUTS:
        if visual.get("kind") in {"source_page", "generated_image"}:
            visual = {"kind": "none", "prompt": None, "source_index": None, "page": None, "alt": None}
            fixed["visual"] = visual
        if anchor.get("kind") in {"source_page", "generated_image"}:
            components = dict(components)
            components["visual_anchor"] = {"kind": "none", "icon_key": None, "caption": None}
            fixed["components"] = components
        return fixed

    if anchor.get("kind") in {"none", None} and visual.get("kind") in {"source_page", "generated_image"}:
        components = dict(components)
        components["visual_anchor"] = {
            "kind": visual.get("kind"),
            "prompt": visual.get("prompt"),
            "source_index": visual.get("source_index"),
            "page": visual.get("page"),
            "alt": visual.get("alt"),
            "caption": visual.get("alt") or fixed.get("title"),
        }
        fixed["components"] = components
    return fixed


def _fit_slide_to_word_budget(slide: dict[str, Any]) -> dict[str, Any]:
    """Trim lower-priority copy until the slide respects the visible word cap."""
    if _slide_visible_word_count(slide) <= MAX_WORDS_PER_SLIDE:
        return slide

    fixed = dict(slide)
    components = fixed.get("components") if isinstance(fixed.get("components"), dict) else {}
    fixed_components = dict(components)
    fixed["components"] = fixed_components

    if fixed.get("subtitle"):
        fixed["subtitle"] = _truncate_words(str(fixed.get("subtitle") or ""), 10)
    _trim_visual_anchor_caption(fixed_components, 8)
    _trim_card_text(fixed_components, heading_words=6, desc_words=10)
    _trim_flow_text(fixed_components, label_words=4, action_words=8)
    _trim_callout_text(fixed_components, 16)
    _trim_metric_text(fixed_components, label_words=5, context_words=7)
    _trim_comparison_text(fixed_components, label_words=4, side_words=8)
    _trim_checklist_text(fixed_components, 9)
    _trim_bullets(fixed, 14)
    if _slide_visible_word_count(fixed) <= MAX_WORDS_PER_SLIDE:
        return fixed

    if fixed.get("subtitle"):
        fixed["subtitle"] = _truncate_words(str(fixed.get("subtitle") or ""), 6)
    _trim_visual_anchor_caption(fixed_components, 5)
    _trim_card_text(fixed_components, heading_words=5, desc_words=7)
    _trim_flow_text(fixed_components, label_words=3, action_words=6)
    _trim_callout_text(fixed_components, 10)
    _trim_metric_text(fixed_components, label_words=4, context_words=5)
    _trim_comparison_text(fixed_components, label_words=3, side_words=6)
    _trim_checklist_text(fixed_components, 6)
    _trim_bullets(fixed, 9)
    if _slide_visible_word_count(fixed) <= MAX_WORDS_PER_SLIDE:
        return fixed

    fixed["title"] = _truncate_words(str(fixed.get("title") or ""), 7)
    _trim_card_text(fixed_components, heading_words=4, desc_words=5)
    _trim_flow_text(fixed_components, label_words=3, action_words=5)
    _trim_callout_text(fixed_components, 8)
    _trim_metric_text(fixed_components, label_words=3, context_words=4)
    _trim_comparison_text(fixed_components, label_words=3, side_words=5)
    _trim_checklist_text(fixed_components, 5)
    _trim_bullets(fixed, 6)
    if _slide_visible_word_count(fixed) <= MAX_WORDS_PER_SLIDE:
        return fixed

    _drop_optional_slide_text(fixed, fixed_components)
    return fixed


def _slide_visible_word_count(slide: dict[str, Any]) -> int:
    visible_text = _visible_strings(
        {
            "title": slide.get("title"),
            "subtitle": slide.get("subtitle"),
            "bullets": slide.get("bullets", []),
            "components": slide.get("components", {}),
            "content": slide.get("content", {}),
        }
    )
    return sum(_word_count(text) for text in visible_text)


def _trim_visual_anchor_caption(components: dict[str, Any], max_words: int) -> None:
    anchor = components.get("visual_anchor")
    if isinstance(anchor, dict) and anchor.get("caption"):
        anchor["caption"] = _truncate_words(str(anchor.get("caption") or ""), max_words)


def _trim_card_text(components: dict[str, Any], *, heading_words: int, desc_words: int) -> None:
    for card in components.get("cards", []):
        if not isinstance(card, dict):
            continue
        card["heading"] = _truncate_words(str(card.get("heading") or ""), heading_words)
        card["desc"] = _truncate_words(str(card.get("desc") or ""), desc_words)


def _trim_flow_text(components: dict[str, Any], *, label_words: int, action_words: int) -> None:
    for step in components.get("flow_steps", []):
        if not isinstance(step, dict):
            continue
        step["label"] = _truncate_words(str(step.get("label") or ""), label_words)
        step["action"] = _repair_action_text(_truncate_words(str(step.get("action") or ""), action_words))


def _trim_callout_text(components: dict[str, Any], max_words: int) -> None:
    callout = components.get("callout_box")
    if isinstance(callout, dict):
        callout["text"] = _truncate_words(str(callout.get("text") or ""), max_words)


def _trim_metric_text(components: dict[str, Any], *, label_words: int, context_words: int) -> None:
    for metric in components.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        metric["value"] = _truncate_words(str(metric.get("value") or ""), 3)
        metric["label"] = _truncate_words(str(metric.get("label") or ""), label_words)
        metric["context"] = _truncate_words(str(metric.get("context") or ""), context_words)


def _trim_comparison_text(components: dict[str, Any], *, label_words: int, side_words: int) -> None:
    for row in components.get("comparison", []):
        if not isinstance(row, dict):
            continue
        row["label"] = _truncate_words(str(row.get("label") or ""), label_words)
        row["left"] = _truncate_words(str(row.get("left") or ""), side_words)
        row["right"] = _truncate_words(str(row.get("right") or ""), side_words)


def _trim_checklist_text(components: dict[str, Any], max_words: int) -> None:
    for item in components.get("checklist", []):
        if isinstance(item, dict):
            item["text"] = _truncate_words(str(item.get("text") or ""), max_words)


def _trim_bullets(slide: dict[str, Any], max_words: int) -> None:
    bullets = slide.get("bullets")
    if isinstance(bullets, list):
        slide["bullets"] = [_truncate_words(str(bullet), max_words) for bullet in bullets[:MAX_BULLETS_PER_SLIDE]]


def _drop_optional_slide_text(slide: dict[str, Any], components: dict[str, Any]) -> None:
    if slide.get("subtitle"):
        slide["subtitle"] = None
    _trim_visual_anchor_caption(components, 0)
    _trim_callout_text(components, 6)
    _trim_card_text(components, heading_words=3, desc_words=4)
    _trim_flow_text(components, label_words=2, action_words=4)
    _trim_metric_text(components, label_words=2, context_words=3)
    _trim_comparison_text(components, label_words=2, side_words=4)
    _trim_checklist_text(components, 4)
    _trim_bullets(slide, 4)


def _repair_card_payload(card: dict[str, Any]) -> dict[str, Any]:
    return {
        **card,
        "heading": _truncate_words(str(card.get("heading") or ""), 7),
        "desc": _truncate_words(str(card.get("desc") or ""), CARD_DESC_MAX_WORDS),
    }


def _repair_flow_step_payload(step: dict[str, Any]) -> dict[str, Any]:
    action = _repair_action_text(str(step.get("action") or ""))
    return {
        **step,
        "label": _truncate_words(str(step.get("label") or ""), 5),
        "action": action,
    }


def _repair_metric_payload(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        **metric,
        "value": _truncate_words(str(metric.get("value") or ""), 4),
        "label": _truncate_words(str(metric.get("label") or ""), 6),
        "context": _truncate_words(str(metric.get("context") or ""), 10),
    }


def _repair_comparison_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "label": _truncate_words(str(row.get("label") or ""), 5),
        "left": _truncate_words(str(row.get("left") or ""), 12),
        "right": _truncate_words(str(row.get("right") or ""), 12),
    }


def _repair_checklist_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "text": _truncate_words(str(item.get("text") or ""), 14),
    }


def _repair_action_text(text: str) -> str:
    shortened = _truncate_words(text, FLOW_ACTION_MAX_WORDS)
    if _looks_action_like(shortened):
        return shortened

    normalized = _normalized_label(text)
    if "cap nhat" in normalized or "update" in normalized:
        return "Cập nhật giao diện"
    if "hien thi" in normalized or "display" in normalized:
        return "Hiển thị bản dịch"
    if "thiet lap" in normalized or "select" in normalized or "locale" in normalized:
        return "Thiết lập locale"
    if "lazy" in normalized or "addressables" in normalized:
        return "Lazy load Addressables"
    if "load" in normalized or "tai" in normalized or "nap" in normalized:
        return "Load tài nguyên"
    if "kiem tra" in normalized or "test" in normalized:
        return "Kiểm tra lỗi"
    if "toi uu" in normalized or "optimize" in normalized:
        return "Tối ưu luồng xử lý"
    return _truncate_words(f"Thực hiện {text}", FLOW_ACTION_MAX_WORDS)


def _truncate_words(text: str, max_words: int) -> str:
    if max_words <= 0:
        return ""
    words = [part for part in re.split(r"\s+", text.strip()) if part]
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).rstrip(" ,;:.") + "."


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
            if key in {"visual", "data_url", "source_index", "page", "prompt", "alt", "kind", "icon_key", "id"}:
                continue
            strings.extend(_visible_strings(item))
        return strings
    return []


def _validate_components_for_layout(slide: SlidePayload) -> None:
    components = slide.components
    layout = slide.layout_type

    if layout == "TITLE_HERO":
        if components.visual_anchor.kind == "none":
            raise ValueError("TITLE_HERO requires a visual_anchor icon, source_page, or generated_image.")
    elif layout == "DUAL_PILLARS":
        if len(components.cards) != 2:
            raise ValueError("DUAL_PILLARS requires exactly 2 cards.")
    elif layout == "GRID_COMPOSITE":
        if len(components.cards) != 3:
            raise ValueError("GRID_COMPOSITE requires exactly 3 cards.")
    elif layout == "PROCESS_FLOW_WITH_CALLOUT":
        if not 3 <= len(components.flow_steps) <= 5:
            raise ValueError("PROCESS_FLOW_WITH_CALLOUT requires 3-5 flow steps.")
        if components.callout_box is None:
            raise ValueError("PROCESS_FLOW_WITH_CALLOUT requires a callout_box.")
    elif layout == "VISUAL_ANCHOR":
        if components.visual_anchor.kind == "none":
            raise ValueError("VISUAL_ANCHOR requires a visual_anchor.")
    elif layout == "METRIC_DASHBOARD":
        if not 3 <= len(components.metrics) <= 5:
            raise ValueError("METRIC_DASHBOARD requires 3-5 metrics.")
    elif layout == "CODE_COMPARISON":
        if not 2 <= len(components.comparison) <= 4:
            raise ValueError("CODE_COMPARISON requires 2-4 comparison rows.")
    elif layout == "CHECKLIST":
        if not 4 <= len(components.checklist) <= 5:
            raise ValueError("CHECKLIST requires 4-5 checklist items.")


def _review_deck_design(deck: SlideDeckPayload) -> list[str]:
    """Deterministic design review used as the repair signal for the composer."""
    issues: list[str] = []
    content_slides = [slide for slide in deck.slides if slide.layout_type != "TRANSITION"]
    anchored_slides = [slide for slide in content_slides if _has_component_anchor(slide)]
    minimum_anchor_count = max(1, math.ceil(len(content_slides) * 0.65))
    if len(anchored_slides) < minimum_anchor_count:
        issues.append(
            f"Too few visual/icon anchors: {len(anchored_slides)} found, need at least {minimum_anchor_count}."
        )

    boxed_streak = 0
    for slide in deck.slides:
        if slide.layout_type in {"DUAL_PILLARS", "GRID_COMPOSITE"} and not _has_component_anchor(slide):
            boxed_streak += 1
            if boxed_streak > 1:
                issues.append("Avoid consecutive text-box slides without strong icons or visuals.")
                break
        else:
            boxed_streak = 0

    if deck.slide_count >= 8 and not any(slide.layout_type == "TRANSITION" for slide in deck.slides):
        issues.append("Decks with 8 or more slides need a TRANSITION slide between major topics.")

    return issues


def _has_component_anchor(slide: SlidePayload) -> bool:
    components = slide.components
    if components.visual_anchor.kind != "none":
        return True
    if any(card.icon_key in ICON_KEYS for card in components.cards):
        return True
    if any(metric.icon_key in ICON_KEYS for metric in components.metrics):
        return True
    if any(item.icon_key in ICON_KEYS for item in components.checklist):
        return True
    return False


def _looks_action_like(text: str) -> bool:
    words = _normalized_label(text).split()
    if not words:
        return False
    action_verbs = {
        "add",
        "bind",
        "cache",
        "call",
        "check",
        "choose",
        "create",
        "disable",
        "enable",
        "fetch",
        "generate",
        "instantiate",
        "lazy",
        "limit",
        "load",
        "map",
        "pool",
        "preload",
        "profile",
        "render",
        "reuse",
        "select",
        "set",
        "split",
        "update",
        "validate",
        "run",
        "detect",
        "translate",
        "display",
        "show",
        "cap",
        "canh",
        "chuyen",
        "chon",
        "dich",
        "doi",
        "dung",
        "giam",
        "gan",
        "goi",
        "hien",
        "kiem",
        "lay",
        "loc",
        "luu",
        "nap",
        "phat",
        "sap",
        "sua",
        "tai",
        "tang",
        "tao",
        "tach",
        "them",
        "thiet",
        "thuc",
        "toi",
        "trich",
        "xoa",
    }
    action_phrases = {
        "cap nhat",
        "canh bao",
        "chuyen doi",
        "dich chuoi",
        "hien thi",
        "kiem tra",
        "phat hien",
        "sap xep",
        "thiet lap",
        "thuc hien",
        "toi uu",
        "trich xuat",
    }
    prose_starters = {"la", "duoc", "co", "this", "the", "a", "an", "he", "system"}
    if words[0] in prose_starters:
        return False
    if len(words) >= 2 and f"{words[0]} {words[1]}" in action_phrases:
        return True
    if words[0] in action_verbs:
        return True
    return False


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
