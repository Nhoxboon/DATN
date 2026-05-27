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
MAX_DECK_OUTPUT_TOKENS = 18000
MAX_WORDS_PER_BULLET = 20
MAX_BULLETS_PER_SLIDE = 4
SLIDE_WIDTH = 1600
SLIDE_HEIGHT = 900
PDF_RENDER_SCALE = 2
FLOW_ACTION_MAX_WORDS = 16
CARD_DESC_MAX_WORDS = 24
CARD_POINT_MAX_WORDS = 14
CARD_MAX_POINTS = 3
CALLOUT_MAX_WORDS = 32
MAX_SOURCE_CROPS_PER_DECK = 6
MIN_CROP_CONFIDENCE = 0.58
SOURCE_VISUAL_PROMOTION_THRESHOLD = 3
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
    "PROCESS_TIMELINE",
    "COMPARISON_TABLE",
    "ICON_GRID",
    "TRANSITION",
}
VISUAL_LAYOUTS = {"TITLE_HERO", "VISUAL_ANCHOR"}
DENSE_LAYOUTS = {
    "GRID_COMPOSITE",
    "PROCESS_FLOW_WITH_CALLOUT",
    "METRIC_DASHBOARD",
    "CODE_COMPARISON",
    "CHECKLIST",
    "PROCESS_TIMELINE",
    "COMPARISON_TABLE",
    "ICON_GRID",
}
MEDIUM_DENSITY_LAYOUTS = {"DUAL_PILLARS", "VISUAL_ANCHOR"}
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
    "activity",
    "braces",
    "bug",
    "boxes",
    "file-json",
    "git-branch",
    "hard-drive",
    "image",
    "languages",
    "lightbulb",
    "memory-stick",
    "mouse-pointer-click",
    "table",
    "wrench",
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
    "activity": "ACT",
    "braces": "{}",
    "bug": "BUG",
    "boxes": "BOX",
    "file-json": "JSON",
    "git-branch": "GIT",
    "hard-drive": "DISK",
    "image": "IMG",
    "languages": "LANG",
    "lightbulb": "IDEA",
    "memory-stick": "MEM",
    "mouse-pointer-click": "UI",
    "table": "TBL",
    "wrench": "TOOL",
}
DANGLING_TRAILING_WORDS = {
    "and",
    "or",
    "to",
    "with",
    "via",
    "through",
    "by",
    "for",
    "in",
    "on",
    "of",
    "tang",
    "giam",
    "va",
    "hoac",
    "de",
    "bang",
    "qua",
    "voi",
    "khi",
    "khong",
    "con",
    "nhung",
    "co",
    "the",
    "gay",
}
SOURCE_VISUAL_STOPWORDS = {
    "and",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "page",
    "slide",
    "image",
    "figure",
    "description",
    "trong",
    "cua",
    "voi",
    "cho",
    "cac",
    "mot",
    "nhung",
    "duoc",
    "khong",
    "hinh",
    "anh",
    "trang",
    "mota",
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
GENERIC_SLIDE_TITLES = {
    "overview",
    "introduction",
    "main idea",
    "key points",
    "content",
    "topic",
    "slide",
    "details",
    "presentation",
    "academic overview from selected sources",
    "tong quan",
    "tong quan hoc thuat",
    "tong quan hoc thuat tu nguon da chon",
    "gioi thieu",
    "noi dung",
    "y chinh",
    "chu de",
}
COVERAGE_TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "Localization Methods": (
        "hardcode",
        "dictionary",
        "json",
        "localization package",
        "string table",
        "asset table",
        "localization table",
    ),
    "Runtime Localization Flow": (
        "game start",
        "localizationsettings",
        "selectedlocale",
        "table database",
        "localized string event",
        "lazy load",
    ),
    "Smart Strings": (
        "smart string",
        "smartformat",
        "playername",
        "plural",
        "choose",
        "variable",
    ),
    "Pseudo Localization": (
        "pseudo localization",
        "hardcode",
        "font",
        "encoding",
        "double byte",
        "ui layout",
    ),
    "Localization Architecture": (
        "namespace",
        "string table collection",
        "addressables",
        "lazy load",
        "asset table collection",
        "production",
    ),
    "Profiler Diagnostics": (
        "profiler",
        "diagnostics",
        "gc alloc",
        "timeline",
        "camera render",
        "frame",
        "ms",
    ),
    "Garbage Collector": (
        "garbage collector",
        "mark phase",
        "sweep phase",
        "managed heap",
        "gc roots",
        "heap",
    ),
    "Object Pooling": (
        "object pooling",
        "objectpool",
        "pool",
        "bullet",
        "projectile",
        "fx",
        "instantiate",
    ),
    "Physics Optimization": (
        "physics",
        "fixed timestep",
        "collision matrix",
        "collider",
        "raycast",
        "layermask",
    ),
    "Rendering And UI Optimization": (
        "gpu",
        "rendering",
        "occlusion culling",
        "texture atlas",
        "rectmask2d",
        "lighting",
        "bake light",
    ),
    "Memory And Asset Management": (
        "memory",
        "assetbundle",
        "asset bundle",
        "addressables",
        "shader",
        "scene",
        "leak",
        "ram",
        "texture",
        "audio",
        "mesh",
    ),
}
ALLOWED_LAYOUTS = COMPONENT_LAYOUTS
CITATION_PATTERN = re.compile(r"\[(?:\d+(?:\s*,\s*\d+)*)\]")
SlideLayoutType = Literal[
    "TITLE_HERO",
    "DUAL_PILLARS",
    "GRID_COMPOSITE",
    "PROCESS_FLOW_WITH_CALLOUT",
    "VISUAL_ANCHOR",
    "METRIC_DASHBOARD",
    "CODE_COMPARISON",
    "CHECKLIST",
    "PROCESS_TIMELINE",
    "COMPARISON_TABLE",
    "ICON_GRID",
    "TRANSITION",
]
SlideIconKey = Literal[
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
    "activity",
    "braces",
    "bug",
    "boxes",
    "file-json",
    "git-branch",
    "hard-drive",
    "image",
    "languages",
    "lightbulb",
    "memory-stick",
    "mouse-pointer-click",
    "table",
    "wrench",
]


class CropBox(BaseModel):
    """Normalized source-page crop rectangle."""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(ge=0, le=1)
    height: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_crop_area(self) -> "CropBox":
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Crop box width and height must be positive.")
        if self.x + self.width > 1.02 or self.y + self.height > 1.02:
            raise ValueError("Crop box must fit inside the normalized page.")
        if self.width * self.height < 0.06:
            raise ValueError("Crop box is too small to be useful.")
        return self


class CropSelectionPayload(BaseModel):
    """Gemini crop-selection response."""

    crop_box: CropBox | None = None
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


class SlideVisual(BaseModel):
    """Visual instruction chosen by the deck planner."""

    kind: Literal["none", "source_page", "generated_image"] = "none"
    prompt: str | None = None
    source_index: int | None = None
    page: int | None = None
    alt: str | None = None
    data_url: str | None = None
    crop_box: CropBox | None = None


class SlideFeature(BaseModel):
    """Short structured text item used by legacy and component layouts."""

    title: str | None = None
    text: str | None = None


class SlideCard(BaseModel):
    """Card component for grid and pillar slides."""

    id: str = ""
    tag: Literal["LEGACY", "MID_LEVEL", "RECOMMENDED", "WARNING", "INSIGHT", "DEFAULT"] = "DEFAULT"
    icon_key: SlideIconKey = "check"
    heading: str = ""
    desc: str = ""
    points: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_card_text(self) -> "SlideCard":
        if _word_count(self.heading) > 7:
            raise ValueError("Card heading must be a label, not a sentence.")
        if _word_count(self.desc) > CARD_DESC_MAX_WORDS:
            raise ValueError(f"Card desc must be at most {CARD_DESC_MAX_WORDS} words.")
        if len(self.points) > CARD_MAX_POINTS:
            raise ValueError(f"Card may contain at most {CARD_MAX_POINTS} points.")
        for point in self.points:
            if _word_count(point) > CARD_POINT_MAX_WORDS:
                raise ValueError(f"Card point must be at most {CARD_POINT_MAX_WORDS} words.")
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

    icon_key: SlideIconKey = "gauge"
    value: str = ""
    label: str = ""
    context: str = ""


class ComparisonItem(BaseModel):
    """Comparison row for code and before/after layouts."""

    icon_key: SlideIconKey = "code"
    label: str = ""
    left: str = ""
    right: str = ""


class ChecklistItem(BaseModel):
    """Checklist row."""

    text: str = ""
    icon_key: SlideIconKey = "check"


class VisualAnchor(BaseModel):
    """Primary visual anchor for a slide."""

    kind: Literal["none", "icon", "source_page", "generated_image"] = "none"
    icon_key: SlideIconKey | None = None
    caption: str | None = None
    prompt: str | None = None
    source_index: int | None = None
    page: int | None = None
    alt: str | None = None
    data_url: str | None = None
    crop_box: CropBox | None = None


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
    layout_type: SlideLayoutType
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
        if not self.title.strip():
            raise ValueError(f"Slide {self.slide_number} must include a visible in-slide title.")
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

        used_source_visuals: set[tuple[int | None, int | None]] = set()
        source_visual_count = 0
        for index, slide in enumerate(self.slides, 1):
            if slide.slide_number != index:
                raise ValueError("Slide numbers must be sequential starting at 1.")

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

        max_source_visuals = min(MAX_SOURCE_CROPS_PER_DECK, max(1, math.ceil(len(self.slides) * 0.5)))
        if source_visual_count > max_source_visuals:
            raise ValueError("Too many source visuals; use them sparingly to avoid visual clutter.")
        return self


class OutlineSlide(BaseModel):
    """One planned slide before detailed composition."""

    slide_number: int
    chapter: str = ""
    layout_type: SlideLayoutType
    title: str = ""
    purpose: str = ""
    visual_strategy: Literal["icon", "source_page", "generated_image", "none"] = "icon"


class CoverageItem(BaseModel):
    """Internal outline mapping from source topic to planned slides."""

    topic: str = ""
    slide_numbers: list[int] = Field(default_factory=list)
    evidence: str = ""


class StoryOutlinePayload(BaseModel):
    """Planner output that fixes the narrative before slide writing."""

    title: str = "Presentation"
    language: str | None = None
    slide_count: int
    chapters: list[str] = Field(default_factory=list)
    slides: list[OutlineSlide]
    coverage_map: list[CoverageItem] = Field(default_factory=list)

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
        coverage_topics = _expected_coverage_topics(context)
        if len(context) > MAX_CONTEXT_CHARS:
            context = _summarize_context(genai_client, app_config.llm.gemini.model, context, document_names)

        visual_candidates = _visual_candidates(chunks)
        deck, outline = _generate_deck(
            genai_client=genai_client,
            model=app_config.llm.gemini.model,
            context=context,
            document_names=document_names,
            visual_candidates=visual_candidates,
            coverage_topics=coverage_topics,
        )
        deck_json = _materialize_visuals(
            deck=deck.model_dump(),
            genai_client=genai_client,
            image_model=app_config.slide_deck.image_model,
            crop_model=app_config.llm.gemini.model,
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
            deck_json["pdf_renderer"] = pdf_renderer
            deck_json.setdefault("pdf_renderer_version", "pillow" if pdf_renderer == "pillow_fallback" else "unknown")

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


def _expected_coverage_topics(context: str) -> list[str]:
    """Detect major source topics that the deck should cover."""
    normalized = _normalized_label(context)
    topics: list[str] = []
    for topic, keywords in COVERAGE_TOPIC_RULES.items():
        score = sum(1 for keyword in keywords if keyword in normalized)
        if score >= _coverage_detection_threshold(topic):
            topics.append(topic)

    localization_topics = [topic for topic in topics if topic.startswith("Localization") or topic in {"Smart Strings", "Pseudo Localization"}]
    optimization_topics = [
        topic
        for topic in topics
        if topic
        in {
            "Profiler Diagnostics",
            "Garbage Collector",
            "Object Pooling",
            "Physics Optimization",
            "Rendering And UI Optimization",
            "Memory And Asset Management",
        }
    ]
    if len(topics) >= 6 or (localization_topics and optimization_topics):
        topics.append("Pre-flight Checklist")
    return list(dict.fromkeys(topics))


def _coverage_detection_threshold(topic: str) -> int:
    if topic in {"Smart Strings", "Pseudo Localization", "Object Pooling"}:
        return 1
    return 2


def _ensure_outline_coverage_map(outline: StoryOutlinePayload, coverage_topics: list[str]) -> None:
    if not coverage_topics:
        return

    existing = {_normalized_label(item.topic): item for item in outline.coverage_map}
    slide_text = {
        slide.slide_number: _normalized_label(" ".join([slide.chapter, slide.title, slide.purpose, slide.layout_type]))
        for slide in outline.slides
    }
    mapped_items: list[CoverageItem] = []
    for topic in coverage_topics:
        existing_item = existing.get(_normalized_label(topic))
        if existing_item and existing_item.slide_numbers:
            mapped_items.append(existing_item)
            continue

        matched_numbers = [
            number
            for number, text in slide_text.items()
            if _topic_match_score(topic, text) > 0 or any(token in text for token in _topic_tokens(topic))
        ]
        if not matched_numbers:
            matched_numbers = [_fallback_coverage_slide_number(topic, outline)]
        mapped_items.append(
            CoverageItem(
                topic=topic,
                slide_numbers=matched_numbers[:2],
                evidence="Mapped from detected source topic and outline slide labels.",
            )
        )
    outline.coverage_map = mapped_items


def _fallback_coverage_slide_number(topic: str, outline: StoryOutlinePayload) -> int:
    if not outline.slides:
        return 1
    if topic == "Pre-flight Checklist":
        checklist = next((slide for slide in outline.slides if slide.layout_type == "CHECKLIST"), None)
        return checklist.slide_number if checklist else outline.slides[-1].slide_number
    non_transition = [slide for slide in outline.slides if slide.layout_type != "TRANSITION"]
    return (non_transition[-1] if non_transition else outline.slides[-1]).slide_number


def _topic_tokens(topic: str) -> list[str]:
    return [token for token in _normalized_label(topic).split() if len(token) > 3]


def _topic_match_score(topic: str, text: str) -> int:
    normalized = _normalized_label(text)
    if topic == "Pre-flight Checklist":
        return int(("checklist" in normalized or "kiem tra" in normalized) and ("profile" in normalized or "localization" in normalized or "memory" in normalized or "physics" in normalized))
    keywords = COVERAGE_TOPIC_RULES.get(topic, ())
    keyword_score = sum(1 for keyword in keywords if keyword in normalized)
    token_score = sum(1 for token in _topic_tokens(topic) if token in normalized)
    return keyword_score + token_score


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
    coverage_topics: list[str] | None = None,
) -> tuple[SlideDeckPayload, StoryOutlinePayload]:
    """Plan a story outline, compose slides, then repair design issues."""
    coverage_topics = coverage_topics if coverage_topics is not None else _expected_coverage_topics(context)
    outline = _generate_story_outline(
        genai_client=genai_client,
        model=model,
        context=context,
        document_names=document_names,
        visual_candidates=visual_candidates,
        coverage_topics=coverage_topics,
    )
    deck = _compose_deck(
        genai_client=genai_client,
        model=model,
        context=context,
        document_names=document_names,
        visual_candidates=visual_candidates,
        outline=outline,
        coverage_topics=coverage_topics,
    )
    _ensure_deck_title(deck, outline, context, document_names, coverage_topics)
    return deck, outline


def _generate_story_outline(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    coverage_topics: list[str],
) -> StoryOutlinePayload:
    """Generate the deck narrative before slide composition."""
    retry_feedback = ""
    last_error: Exception | None = None

    for _attempt in range(MAX_DECK_ATTEMPTS):
        response = genai_client.models.generate_content(
            model=model,
            contents=_outline_prompt(context, document_names, visual_candidates, coverage_topics, retry_feedback),
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
                outline = parsed_payload
            else:
                outline = StoryOutlinePayload.model_validate(parsed_payload)
            _ensure_outline_coverage_map(outline, coverage_topics)
            return outline
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            retry_feedback = (
                "\nYour previous outline failed validation. Return corrected JSON only. "
                f"Validation error: {exc}\n"
            )

    logger.warning("Falling back to deterministic slide outline after Gemini outline failures: %s", last_error)
    return _fallback_story_outline(context=context, document_names=document_names, coverage_topics=coverage_topics)


def _fallback_story_outline(
    *,
    context: str,
    document_names: list[str],
    coverage_topics: list[str],
) -> StoryOutlinePayload:
    """Build a conservative outline when the model returns malformed planner JSON."""
    vietnamese = _looks_vietnamese(context)
    topics = _ordered_outline_topics(coverage_topics)
    if not topics:
        topics = _default_outline_topics()

    localization_topics = [topic for topic in topics if _outline_chapter_key(topic) == "localization"]
    optimization_topics = [topic for topic in topics if _outline_chapter_key(topic) != "localization"]
    wants_transition = bool(localization_topics and optimization_topics)
    max_topic_slides = MAX_SLIDES - 1 - int(wants_transition)

    selected_topics = topics[:max_topic_slides]
    while len(selected_topics) < MIN_SLIDES - 1:
        for topic in _default_outline_topics():
            if topic not in selected_topics:
                selected_topics.append(topic)
                break
        else:
            break
    selected_topics = selected_topics[:max_topic_slides]

    selected_localization = [topic for topic in selected_topics if _outline_chapter_key(topic) == "localization"]
    selected_optimization = [topic for topic in selected_topics if _outline_chapter_key(topic) != "localization"]
    include_transition = bool(selected_localization and selected_optimization and len(selected_topics) + 2 <= MAX_SLIDES)

    slides: list[dict[str, Any]] = [
        {
            "slide_number": 1,
            "chapter": _chapter_title("hero", vietnamese),
            "layout_type": "TITLE_HERO",
            "title": _fallback_deck_title(context, document_names, coverage_topics, vietnamese),
            "purpose": "Open the deck with the central theme.",
            "visual_strategy": "icon",
        }
    ]

    ordered_selected = selected_localization if include_transition else selected_topics
    if include_transition:
        ordered_selected = [*selected_localization, "__TRANSITION__", *selected_optimization]

    for topic in ordered_selected:
        if topic == "__TRANSITION__":
            slides.append(
                {
                    "slide_number": len(slides) + 1,
                    "chapter": _chapter_title("optimization", vietnamese),
                    "layout_type": "TRANSITION",
                    "title": _transition_title(vietnamese),
                    "purpose": "Signal the chapter shift.",
                    "visual_strategy": "none",
                }
            )
            continue
        chapter_key = _outline_chapter_key(topic)
        slides.append(
            {
                "slide_number": len(slides) + 1,
                "chapter": _chapter_title(chapter_key, vietnamese),
                "layout_type": _fallback_layout_for_topic(topic),
                "title": _fallback_title_for_topic(topic, vietnamese),
                "purpose": _fallback_purpose_for_topic(topic, vietnamese),
                "visual_strategy": "icon",
            }
        )

    outline = StoryOutlinePayload.model_validate(
        {
            "title": _fallback_deck_title(context, document_names, coverage_topics, vietnamese),
            "language": "Vietnamese" if vietnamese else "English",
            "slide_count": len(slides),
            "chapters": list(dict.fromkeys(str(slide["chapter"]) for slide in slides if slide.get("chapter"))),
            "slides": slides,
            "coverage_map": [],
        }
    )
    _ensure_outline_coverage_map(outline, coverage_topics)
    return outline


def _ordered_outline_topics(coverage_topics: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    priority = [
        "Localization Methods",
        "Localization Architecture",
        "Runtime Localization Flow",
        "Smart Strings",
        "Pseudo Localization",
        "Profiler Diagnostics",
        "Garbage Collector",
        "Object Pooling",
        "Physics Optimization",
        "Rendering And UI Optimization",
        "Memory And Asset Management",
        "Pre-flight Checklist",
    ]
    for topic in [*priority, *coverage_topics]:
        if topic in coverage_topics and topic not in seen:
            ordered.append(topic)
            seen.add(topic)
    return ordered


def _default_outline_topics() -> list[str]:
    return [
        "Localization Architecture",
        "Runtime Localization Flow",
        "Localization Methods",
        "Memory And Asset Management",
    ]


def _outline_chapter_key(topic: str) -> str:
    normalized = _normalized_label(topic)
    if any(marker in normalized for marker in ("localization", "smart", "pseudo")):
        return "localization"
    return "optimization"


def _fallback_layout_for_topic(topic: str) -> str:
    if topic in {"Runtime Localization Flow", "Garbage Collector"}:
        return "PROCESS_TIMELINE"
    if topic in {"Localization Methods", "Pseudo Localization"}:
        return "COMPARISON_TABLE"
    if topic == "Profiler Diagnostics":
        return "VISUAL_ANCHOR"
    if topic == "Pre-flight Checklist":
        return "CHECKLIST"
    return "ICON_GRID"


def _fallback_title_for_topic(topic: str, vietnamese: bool) -> str:
    if not vietnamese:
        return topic
    titles = {
        "Localization Methods": "So sánh Phương pháp Localization",
        "Localization Architecture": "Kiến trúc Hệ thống Localization",
        "Runtime Localization Flow": "Luồng Runtime của Localization",
        "Smart Strings": "Smart Strings và Chuỗi Động",
        "Pseudo Localization": "Pseudo Localization cho Kiểm thử",
        "Profiler Diagnostics": "Chẩn đoán Hiệu suất bằng Profiler",
        "Garbage Collector": "Vòng đời Garbage Collector",
        "Object Pooling": "Object Pooling giảm Instantiate",
        "Physics Optimization": "Tối ưu Physics và Collision",
        "Rendering And UI Optimization": "Tối ưu Rendering và UI",
        "Memory And Asset Management": "Quản lý Memory và Asset",
        "Pre-flight Checklist": "Checklist trước khi Production",
    }
    return titles.get(topic, topic)


def _fallback_purpose_for_topic(topic: str, vietnamese: bool) -> str:
    if vietnamese:
        return f"Tóm lược ý chính và quyết định kỹ thuật cho {topic}."
    return f"Summarize the key claims and technical decisions for {topic}."


def _chapter_title(chapter_key: str, vietnamese: bool) -> str:
    if chapter_key == "localization":
        return "Localization" if not vietnamese else "Localization"
    if chapter_key == "optimization":
        return "Optimization" if not vietnamese else "Tối ưu hóa"
    return "Core Theme" if not vietnamese else "Chủ đề chính"


def _ensure_deck_title(
    deck: SlideDeckPayload,
    outline: StoryOutlinePayload,
    context: str,
    document_names: list[str],
    coverage_topics: list[str],
) -> None:
    """Replace generic deck/hero titles with source-specific titles."""
    vietnamese = _looks_vietnamese(context) or _looks_vietnamese(deck.title) or _looks_vietnamese(outline.title)
    inferred_title = _fallback_deck_title(context, document_names, coverage_topics, vietnamese)
    outline_title = outline.title.strip()
    if _is_generic_deck_title(outline_title):
        outline_title = ""
    replacement = outline_title or inferred_title

    if _is_generic_deck_title(deck.title):
        deck.title = replacement
    if deck.slides and deck.slides[0].layout_type == "TITLE_HERO" and _is_generic_deck_title(deck.slides[0].title):
        deck.slides[0].title = deck.title or replacement


def _fallback_deck_title(
    context: str,
    document_names: list[str],
    coverage_topics: list[str],
    vietnamese: bool,
) -> str:
    normalized_context = _normalized_label(" ".join([context, *document_names, *coverage_topics]))
    has_unity = "unity" in normalized_context
    has_localization = any(_outline_chapter_key(topic) == "localization" for topic in coverage_topics) or any(
        marker in normalized_context
        for marker in (
            "localization",
            "locale",
            "string table",
            "asset table",
            "pseudo localization",
            "smart strings",
        )
    )
    has_optimization = any(_outline_chapter_key(topic) == "optimization" for topic in coverage_topics) or any(
        marker in normalized_context
        for marker in (
            "optimization",
            "performance",
            "profiler",
            "garbage collector",
            "object pooling",
            "physics",
            "rendering",
            "memory",
            "hieu suat",
            "toi uu",
        )
    )
    has_audio = any(marker in normalized_context for marker in ("audio", "sound", "am thanh"))
    has_rag = any(marker in normalized_context for marker in ("rag", "retrieval", "vector", "embedding"))

    if vietnamese:
        unity_suffix = " trong Unity" if has_unity else ""
        if has_localization and has_optimization:
            return f"Hệ thống Localization và Tối ưu hóa Hiệu suất{unity_suffix}"
        if has_localization:
            return f"Hệ thống Localization{unity_suffix}"
        if has_optimization:
            return f"Tối ưu hóa Hiệu suất{unity_suffix}"
        if has_audio:
            return f"Làm chủ Âm thanh{unity_suffix}"
        if has_rag:
            return "Kiến trúc RAG và Truy xuất Tri thức"
        return _document_title_from_names(document_names) or "Tổng quan Nội dung từ Nguồn đã chọn"

    unity_suffix = " in Unity" if has_unity else ""
    if has_localization and has_optimization:
        return f"Unity Localization and Performance Optimization" if has_unity else "Localization and Performance Optimization"
    if has_localization:
        return f"Localization Systems{unity_suffix}"
    if has_optimization:
        return f"Performance Optimization{unity_suffix}"
    if has_audio:
        return f"Audio Systems{unity_suffix}"
    if has_rag:
        return "RAG Architecture and Knowledge Retrieval"
    return _document_title_from_names(document_names) or "Source-Grounded Presentation"


def _document_title_from_names(document_names: list[str]) -> str:
    for name in document_names:
        stem = Path(name).stem.replace("_", " ").replace("-", " ").strip()
        if stem and not _is_generic_deck_title(stem):
            return stem[:72]
    return ""


def _transition_title(vietnamese: bool) -> str:
    if vietnamese:
        return "Từ hệ thống nội dung đến hiệu suất vận hành"
    return "From content systems to runtime performance"


def _looks_vietnamese(text: str) -> bool:
    normalized = text.casefold()
    return bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", normalized)) or any(
        marker in normalized for marker in (" và ", " của ", " không ", " trong ", " được ")
    )


def _compose_deck(
    *,
    genai_client: genai.Client,
    model: str,
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    outline: StoryOutlinePayload,
    coverage_topics: list[str],
) -> SlideDeckPayload:
    """Generate and validate a strict deck JSON payload."""
    retry_feedback = ""
    last_error: Exception | None = None
    last_review_issues: list[str] = []
    deck: SlideDeckPayload | None = None

    for attempt in range(MAX_DECK_ATTEMPTS):
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
            review_issues = _review_deck_design(deck, coverage_topics=coverage_topics)
            if review_issues:
                last_review_issues = review_issues
                if attempt >= MAX_DECK_ATTEMPTS - 1:
                    logger.warning(
                        "Accepting slide deck after design-review retries were exhausted issues=%s",
                        "; ".join(review_issues),
                    )
                    _fill_empty_visual_anchor_fallbacks(deck)
                    return deck
                retry_feedback = _deck_design_review_feedback(review_issues)
                continue
            return deck
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            retry_feedback = (
                "\nYour previous JSON failed validation. Return a corrected JSON object only. "
                f"Validation error: {exc}\n"
            )

    if last_review_issues and deck:
        _fill_empty_visual_anchor_fallbacks(deck)
        return deck
    raise ValueError(f"Gemini did not return a valid slide deck: {last_error}")


def _outline_prompt(
    context: str,
    document_names: list[str],
    visual_candidates: list[dict[str, Any]],
    coverage_topics: list[str],
    retry_feedback: str,
) -> str:
    visual_text = _visual_candidates_text(visual_candidates)
    topic_text = "\n".join(f"- {topic}" for topic in coverage_topics) if coverage_topics else "- Auto-detect from context."
    slide_count_guidance = (
        "Prefer 11-12 slides because the selected sources contain many distinct technical topics."
        if len(coverage_topics) >= 7 or len(document_names) >= 2
        else "Use the fewest slides that still covers every major topic."
    )

    return f"""
You are the Story Outline Planner for a NotebookLM-quality academic presentation.

Use only the supplied context. Auto-detect the main language and write in that language.

Planning goals:
- Choose {MIN_SLIDES}-{MAX_SLIDES} slides.
- {slide_count_guidance}
- Build a clear story with chapters, not a list of extracted headings.
- Plan every slide as self-contained: the title must be visible inside the slide page, not only in navigation.
- Use a meaningful message headline whenever possible; avoid generic titles like "Overview", "Key Points", or "Details".
- If there are two or more major topics, add exactly one TRANSITION slide at the chapter boundary.
- Do not compress unrelated chapters into one slide just to save slide count.
- Assign each slide one visual strategy: icon, source_page, generated_image, or none.
- Do not plan a final generic summary/recap/conclusion slide.
- Create coverage_map: every detected coverage topic below must map to at least one planned slide.
- A grounded final CHECKLIST is allowed only when it is action-oriented; it must not be a generic summary.

Research-based layout rules:
- Use one core idea per slide, supported by visual evidence, compact components, or a short table.
- Use hierarchy, spacing, scale, contrast, and grid alignment to guide attention.
- Process/runtime/lifecycle content must use PROCESS_TIMELINE or PROCESS_FLOW_WITH_CALLOUT.
- Comparison/opposition/legacy-vs-recommended content must use COMPARISON_TABLE or DUAL_PILLARS.
- Three independent ideas should use GRID_COMPOSITE.
- Exactly four independent ideas must use ICON_GRID; the renderer will show them as a balanced 2x2 grid.
- Five or six independent ideas must use ICON_GRID as a compact 3x2 grid.
- Transition/slogan slides must use TRANSITION with centered, large typography.

Allowed layout_type values:
- TITLE_HERO
- DUAL_PILLARS
- GRID_COMPOSITE
- PROCESS_FLOW_WITH_CALLOUT
- VISUAL_ANCHOR
- METRIC_DASHBOARD
- CODE_COMPARISON
- CHECKLIST
- PROCESS_TIMELINE
- COMPARISON_TABLE
- ICON_GRID
- TRANSITION

Return only valid JSON matching the response schema.

Selected documents: {", ".join(document_names)}

Detected coverage topics:
{topic_text}

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
- Every slide must be self-contained: its title is rendered inside the slide canvas, not only in the sidebar.
- Write meaningful message headlines; avoid generic titles like "Overview", "Key Points", "Details", or "Content".
- Keep one core idea per slide and support it with visual evidence, compact components, icons, tables, or timelines.
- Use hierarchy, spacing, scale, contrast, and grid alignment to guide attention.
- Every technical concept should be expressed as Action, Technique, Metric, Comparison, or Callout.
- Use visual anchors: icon_key on cards/metrics/checklists, source_page only when clearly useful, generated_image only for a hero/concept slide.
- Use at most one generated_image in the whole deck; all other keyword visuals must be icon_key.
- Prefer source_page over generated_image when a candidate page contains a relevant diagram, chart, profiler view, table, code, or flow; the worker will crop the page automatically.
- source_page and generated_image are allowed only on TITLE_HERO or VISUAL_ANCHOR slides; every other layout must set visual.kind="none" and components.visual_anchor.kind="none" unless it uses card/metric/checklist icons.
- Cover every topic from the approved coverage_map; do not skip Profiler/GC/Object Pooling/Physics/Rendering/Memory/Localization topics when present.
- Prefer rich layouts for dense technical evidence: PROCESS_TIMELINE for runtime/GC/loading flow, COMPARISON_TABLE for methods/best-practices/before-after, ICON_GRID for many small techniques, plus METRIC_DASHBOARD/CODE_COMPARISON/CHECKLIST.
- Process/runtime/lifecycle content must use PROCESS_TIMELINE or PROCESS_FLOW_WITH_CALLOUT.
- Comparison/opposition/legacy-vs-recommended content must use COMPARISON_TABLE or DUAL_PILLARS.
- Three independent ideas should use GRID_COMPOSITE.
- Exactly four independent ideas must use ICON_GRID so the renderer can show a balanced 2x2 grid.
- Five or six independent ideas must use ICON_GRID as a compact 3x2 grid.
- TRANSITION slides are for chapter shifts or slogan-like statements only.
- Do not overuse sparse DUAL_PILLARS; use it only for exactly two large ideas.
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
- PROCESS_TIMELINE
- COMPARISON_TABLE
- ICON_GRID
- TRANSITION

Component rules:
- GRID_COMPOSITE: exactly 3 cards with id, tag, icon_key, heading, desc, and 1-2 short points when no source visual is used.
- DUAL_PILLARS: 2 cards; each card must have icon_key, heading, desc, and 1-2 short points when no source visual is used.
- Card points are for compact examples, commands, names, numbers, or caveats; never full prose.
- PROCESS_FLOW_WITH_CALLOUT: 3-5 flow_steps and one callout_box.
- PROCESS_TIMELINE: 5-7 flow_steps; use for Localization Runtime Flow, GC phases, loading or optimization pipelines.
- flow_steps.step must be a numeric string only ("1", "2", "3"...); put words in label/action.
- VISUAL_ANCHOR: components.visual_anchor must be icon, source_page, or generated_image and include a short caption.
- VISUAL_ANCHOR must also include either 1-2 explanatory cards with points or one callout_box; never return an icon/caption-only slide.
- METRIC_DASHBOARD: 3-5 metrics with icon_key, value, label, context.
- CODE_COMPARISON: 2-4 comparison rows with label, left, right.
- COMPARISON_TABLE: 3-5 comparison rows; every row must include icon_key, label, left, right. Use the full table area with substantive technical cells, not one-word entries.
- CHECKLIST: 4-5 checklist items with icon_key and command-like text.
- ICON_GRID: 4-6 cards with icon_key, heading, desc, and 1-3 short points; exactly 4 cards render as 2x2, 5-6 cards render as 3x2.
- TRANSITION: title and subtitle only; keep components empty.
- Card object format: {{"id":"01","tag":"INSIGHT","icon_key":"cpu","heading":"Profiler","desc":"Trace spikes before optimizing.","points":["Watch GC.Alloc","Check frame timeline"]}}.

Text constraints:
- Card desc <= {CARD_DESC_MAX_WORDS} words.
- Card points <= {CARD_MAX_POINTS} per card and <= {CARD_POINT_MAX_WORDS} words each.
- Flow step action <= {FLOW_ACTION_MAX_WORDS} words and must sound command-like.
- Callout text <= {CALLOUT_MAX_WORDS} words.
- Vietnamese flow actions should start with imperative verbs like "Cập nhật", "Thiết lập", "Tải", "Nạp", "Hiển thị", "Kiểm tra", "Tách", or "Tối ưu".
- There is no fixed total word cap per slide; include enough grounded detail to make each slide useful.
- Dense layouts should use their available area: fill tables with 3-5 meaningful rows, grids with points, and timelines with concrete actions.
- Keep text focused on main claims, keywords, mechanisms, tradeoffs, examples, and caveats from the source; do not add filler or long prose.
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


def _deck_design_review_feedback(review_issues: list[str]) -> str:
    issue_text = "\n".join(f"- {issue}" for issue in review_issues)
    return f"""
Your previous JSON was structurally valid, but the deck design review found issues:
{issue_text}

Return corrected JSON only. Keep the same slide_count. For the numbered sparse or DUAL_PILLARS slides:
- Replace broad card-frame slides with PROCESS_TIMELINE, COMPARISON_TABLE, or ICON_GRID when the topic has multiple details.
- Add 2-3 card points where a card layout remains appropriate.
- Keep generated_image at most once; use icon_key for keyword visuals.
- Do not drop coverage topics while changing layouts.
""".strip()


def _visual_candidates_text(visual_candidates: list[dict[str, Any]]) -> str:
    candidate_lines = []
    for candidate in visual_candidates[:24]:
        excerpt = str(candidate.get("excerpt") or "").strip()
        excerpt_text = f"; excerpt={excerpt}" if excerpt else ""
        candidate_lines.append(
            f"- source_index={candidate['source_index']}; document={candidate['document_name']}; "
            f"pages={candidate['page_range']}; page={candidate.get('page') or 'unknown'}{excerpt_text}"
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
    elif layout == "PROCESS_TIMELINE":
        _render_process_timeline(draw, slide, body_font, small_font)
    elif layout == "COMPARISON_TABLE":
        _render_comparison_table(draw, slide, body_font, small_font)
    elif layout == "ICON_GRID":
        _render_icon_grid(draw, slide, body_font, small_font)
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
        draw.text((x + 22, y + 24), str(index + 1), font=small_font, fill="#d89c2b")
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
    y = 255
    if caption:
        y = _draw_wrapped(draw, caption, (995, y), body_font, "#2b3437", 430, 8) + 32
    for point in _visual_anchor_points(slide)[:4]:
        draw.ellipse((1002, y + 12, 1014, y + 24), fill="#d89c2b")
        y = _draw_wrapped(draw, point, (1030, y), small_font, "#2b3437", 390, 5) + 10
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


def _render_process_timeline(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    steps = _component_flow_steps(slide)[:7]
    if not steps:
        return
    x_start = 95
    y = 275
    available_width = 1410
    gap = 12
    step_width = int((available_width - gap * (len(steps) - 1)) / len(steps))
    y_line = y + 64
    draw.line((x_start + 20, y_line, x_start + available_width - 20, y_line), fill="#c7d5da", width=4)
    for index, step in enumerate(steps):
        x = x_start + index * (step_width + gap)
        draw.rounded_rectangle((x, y, x + step_width, y + 250), radius=16, fill="#ffffff", outline="#d9e2e6", width=2)
        draw.ellipse((x + 16, y + 34, x + 58, y + 76), fill="#1f5666")
        draw.text((x + 30, y + 46), str(index + 1), font=small_font, fill="#ffffff")
        _draw_wrapped(draw, str(step.get("label") or ""), (x + 16, y + 98), small_font, "#1f5666", step_width - 32, 5)
        _draw_wrapped(draw, str(step.get("action") or ""), (x + 16, y + 165), small_font, "#2b3437", step_width - 32, 5)
    callout = _component_callout(slide)
    if callout:
        _draw_callout(draw, callout, (180, 610, 1420, 760), small_font, small_font)


def _render_comparison_table(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    rows = _component_comparison(slide)[:5]
    if not rows:
        return
    columns = _comparison_table_columns(rows)
    x1, y1, x2, y2 = (95, 195, 1505, 780)
    draw.rounded_rectangle((x1, y1, x2, y2), radius=20, fill="#ffffff", outline="#d9e2e6", width=2)
    header_height = 70
    draw.rectangle((x1, y1, x2, y1 + header_height), fill="#1f5666")
    column_boxes = _comparison_table_column_boxes(x1, x2, columns)
    for column, (col_x1, _col_x2) in zip(columns, column_boxes):
        draw.text((col_x1 + 22, y1 + 24), column["header"], font=small_font, fill="#ffffff")
    row_height = int((y2 - y1 - header_height) / max(len(rows), 1))
    y = y1 + header_height
    for index, row in enumerate(rows):
        fill = "#f7fafb" if index % 2 else "#ffffff"
        draw.rectangle((x1, y, x2, y + row_height), fill=fill)
        for column, (col_x1, col_x2) in zip(columns, column_boxes):
            text_x = col_x1 + 22
            max_width = col_x2 - col_x1 - 44
            if column["key"] == "label":
                _draw_icon_badge(draw, str(row.get("icon_key") or "code"), (col_x1 + 22, y + 28), small_font)
                text_x = col_x1 + 92
                max_width = col_x2 - col_x1 - 114
                fill_color = "#1f5666"
            else:
                fill_color = "#2b3437"
            _draw_wrapped(draw, str(row.get(column["key"]) or ""), (text_x, y + 28), small_font, fill_color, max_width, 5)
        y += row_height


def _comparison_table_columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    if any(str(row.get("label") or "").strip() for row in rows):
        columns.append({"key": "label", "header": "Focus"})
    if any(str(row.get("left") or "").strip() for row in rows):
        columns.append({"key": "left", "header": "Baseline"})
    if any(str(row.get("right") or "").strip() for row in rows):
        columns.append({"key": "right", "header": "Recommended"})
    return columns or [{"key": "right", "header": "Recommended"}]


def _comparison_table_column_boxes(x1: int, x2: int, columns: list[dict[str, str]]) -> list[tuple[int, int]]:
    if len(columns) == 1:
        weights = [1.0]
    elif len(columns) == 2:
        weights = [1.0, 1.0]
    else:
        weights = [0.78, 1.05, 1.25]
    total = sum(weights)
    width = x2 - x1
    boxes: list[tuple[int, int]] = []
    cursor = x1
    for index, weight in enumerate(weights):
        next_x = x2 if index == len(weights) - 1 else int(cursor + width * weight / total)
        boxes.append((cursor, next_x))
        cursor = next_x
    return boxes


def _render_icon_grid(
    draw: ImageDraw.ImageDraw,
    slide: dict[str, Any],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    cards = _component_cards(slide)[:6]
    boxes = _icon_grid_boxes(len(cards))
    for index, card in enumerate(cards):
        _draw_compact_icon_card(draw, card, boxes[index], body_font, small_font)


def _icon_grid_boxes(card_count: int) -> list[tuple[int, int, int, int]]:
    if card_count == 4:
        return [
            (250, 220, 760, 445),
            (840, 220, 1350, 445),
            (250, 495, 760, 720),
            (840, 495, 1350, 720),
        ]
    return [
        (95, 215, 545, 425),
        (575, 215, 1025, 425),
        (1055, 215, 1505, 425),
        (95, 485, 545, 715),
        (575, 485, 1025, 715),
        (1055, 485, 1505, 715),
    ]


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
    y = _draw_wrapped(draw, str(card.get("desc") or ""), (x1 + 36, y1 + 235), small_font, "#2b3437", x2 - x1 - 72, 7)
    points = [str(point) for point in card.get("points", []) if str(point).strip()] if isinstance(card.get("points"), list) else []
    for point in points[:CARD_MAX_POINTS]:
        draw.ellipse((x1 + 40, y + 16, x1 + 50, y + 26), fill=accent)
        y = _draw_wrapped(draw, point, (x1 + 66, y), small_font, "#2b3437", x2 - x1 - 102, 5) + 7


def _draw_compact_icon_card(
    draw: ImageDraw.ImageDraw,
    card: dict[str, Any],
    box: tuple[int, int, int, int],
    body_font: ImageFont.ImageFont,
    small_font: ImageFont.ImageFont,
) -> None:
    tag = str(card.get("tag") or "DEFAULT")
    fill, outline, accent = _tag_style(tag)
    x1, y1, x2, _y2 = box
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=2)
    _draw_icon_badge(draw, str(card.get("icon_key") or "check"), (x1 + 24, y1 + 24), small_font, fill=accent)
    _draw_wrapped(draw, str(card.get("heading") or ""), (x1 + 92, y1 + 26), body_font, "#1f5666", x2 - x1 - 125, 5)
    y = _draw_wrapped(draw, str(card.get("desc") or ""), (x1 + 24, y1 + 98), small_font, "#2b3437", x2 - x1 - 48, 5)
    points = [str(point) for point in card.get("points", []) if str(point).strip()] if isinstance(card.get("points"), list) else []
    for point in points[:CARD_MAX_POINTS]:
        draw.ellipse((x1 + 28, y + 14, x1 + 37, y + 23), fill=accent)
        y = _draw_wrapped(draw, point, (x1 + 50, y), small_font, "#2b3437", x2 - x1 - 74, 4) + 4


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


def _visual_anchor_points(slide: dict[str, Any]) -> list[str]:
    points: list[str] = []
    for card in _component_cards(slide):
        heading = str(card.get("heading") or "").strip()
        for point in card.get("points", []) if isinstance(card.get("points"), list) else []:
            point_text = str(point).strip()
            if point_text:
                points.append(f"{heading}: {point_text}" if heading else point_text)
        if not card.get("points") and card.get("desc"):
            points.append(str(card.get("desc") or ""))
    for item in _component_checklist(slide):
        if item.get("text"):
            points.append(str(item.get("text")))
    return points


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
    candidates = [text]
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    first_error: json.JSONDecodeError | None = None
    parsed: Any = None
    for candidate in candidates:
        for attempt in (candidate, _repair_json_delimiters(candidate)):
            try:
                parsed = json.loads(attempt)
                break
            except json.JSONDecodeError as exc:
                first_error = first_error or exc
        if parsed is not None:
            break
    if parsed is None:
        if first_error:
            raise first_error
        raise ValueError("Expected a JSON object from Gemini.")
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from Gemini.")
    return parsed


def _repair_json_delimiters(text: str) -> str:
    """Repair common Gemini JSON delimiter slips before retrying strict json.loads."""
    repaired = re.sub(r",(\s*[}\]])", r"\1", text)
    repaired = re.sub(r"}(\s*\n\s*){", r"},\1{", repaired)
    repaired = re.sub(r"\](\s*\n\s*){", r"],\1{", repaired)
    repaired = re.sub(r"(true|false|null|[}\]\"0-9])(\s*\n\s*)(\"[A-Za-z_][A-Za-z0-9_]*\"\s*:)", r"\1,\2\3", repaired)
    return repaired


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


def _repair_card_payload(card: dict[str, Any]) -> dict[str, Any]:
    points = card.get("points")
    repaired_points = [
        _truncate_words(str(point), CARD_POINT_MAX_WORDS)
        for point in points[:CARD_MAX_POINTS]
        if str(point).strip()
    ] if isinstance(points, list) else []
    return {
        **card,
        "heading": _truncate_words(str(card.get("heading") or ""), 7),
        "desc": _truncate_words(str(card.get("desc") or ""), CARD_DESC_MAX_WORDS),
        "points": repaired_points,
    }


def _repair_flow_step_payload(step: dict[str, Any]) -> dict[str, Any]:
    action = _repair_action_text(str(step.get("action") or ""))
    return {
        **step,
        "step": _normalize_flow_step_marker(step.get("step")),
        "label": _truncate_words(str(step.get("label") or ""), 5),
        "action": action,
    }


def _repair_metric_payload(metric: dict[str, Any]) -> dict[str, Any]:
    return {
        **metric,
        "value": _truncate_words(str(metric.get("value") or ""), 4),
        "label": _truncate_words(str(metric.get("label") or ""), 6),
        "context": _truncate_words(str(metric.get("context") or ""), 14),
    }


def _repair_comparison_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "label": _truncate_words(str(row.get("label") or ""), 8),
        "left": _truncate_words(str(row.get("left") or ""), 22),
        "right": _truncate_words(str(row.get("right") or ""), 22),
    }


def _repair_checklist_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "text": _truncate_words(str(item.get("text") or ""), 18),
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
        return _clean_dangling_text(text.strip())
    return _clean_truncated_text(words[:max_words])


def _clean_truncated_text(words: list[str]) -> str:
    return _clean_dangling_words(words, add_period=True)


def _clean_dangling_text(text: str) -> str:
    words = [part for part in re.split(r"\s+", text.strip()) if part]
    if not words:
        return ""
    return _clean_dangling_words(words, add_period=False)


def _clean_dangling_words(words: list[str], *, add_period: bool) -> str:
    removed = False
    while len(words) > 1:
        last = re.sub(r"[.,;:!?]+$", "", words[-1])
        if _normalized_label(last) not in DANGLING_TRAILING_WORDS:
            break
        words.pop()
        removed = True
    cleaned = " ".join(words).rstrip(" ,;:.")
    if add_period or removed:
        return f"{cleaned}."
    return cleaned


def _normalize_flow_step_marker(value: Any) -> str:
    match = re.search(r"\d+", str(value or ""))
    return match.group(0) if match else ""


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
            if key in {"visual", "data_url", "source_index", "page", "prompt", "alt", "kind", "icon_key", "id", "step"}:
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
    elif layout == "PROCESS_TIMELINE":
        if not 5 <= len(components.flow_steps) <= 7:
            raise ValueError("PROCESS_TIMELINE requires 5-7 flow steps.")
    elif layout == "COMPARISON_TABLE":
        if not 3 <= len(components.comparison) <= 5:
            raise ValueError("COMPARISON_TABLE requires 3-5 comparison rows.")
    elif layout == "ICON_GRID":
        if not 4 <= len(components.cards) <= 6:
            raise ValueError("ICON_GRID requires 4-6 cards.")


def _review_deck_design(deck: SlideDeckPayload, coverage_topics: list[str] | None = None) -> list[str]:
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

    repeated_layout_issue = _consecutive_layout_issue(deck.slides)
    if repeated_layout_issue:
        issues.append(repeated_layout_issue)

    if deck.slide_count >= 8 and not any(slide.layout_type == "TRANSITION" for slide in deck.slides):
        issues.append("Decks with 8 or more slides need a TRANSITION slide between major topics.")

    if deck.slide_count >= 8:
        sparse_slides = [slide for slide in content_slides if _is_sparse_slide(slide)]
        if len(sparse_slides) > 2:
            numbers = ", ".join(str(slide.slide_number) for slide in sparse_slides[:4])
            issues.append(f"Too many sparse large-frame slides: {numbers}. Add card points, metrics, comparison rows, or a source visual.")

    dual_pillar_count = sum(1 for slide in deck.slides if slide.layout_type == "DUAL_PILLARS")
    if dual_pillar_count > 2:
        issues.append(f"Too many DUAL_PILLARS slides: {dual_pillar_count} found, maximum is 2.")

    legacy_box_count = sum(1 for slide in content_slides if slide.layout_type in {"DUAL_PILLARS", "GRID_COMPOSITE"})
    rich_layout_count = sum(1 for slide in content_slides if slide.layout_type in {"PROCESS_TIMELINE", "COMPARISON_TABLE", "ICON_GRID"})
    if len(content_slides) >= 8 and legacy_box_count > max(3, math.ceil(len(content_slides) * 0.45)) and rich_layout_count < 2:
        issues.append("Too many old card-frame layouts; use PROCESS_TIMELINE, COMPARISON_TABLE, or ICON_GRID for dense topics.")

    for slide in deck.slides:
        if not slide.title.strip():
            issues.append(f"Slide {slide.slide_number} is missing an in-slide title.")
        elif slide.layout_type not in {"TITLE_HERO", "TRANSITION"} and _is_generic_slide_title(slide.title):
            issues.append(f"Slide {slide.slide_number} title is too generic; write a message headline that names the slide's point.")

        if _is_empty_visual_anchor_slide(slide):
            issues.append(
                f"Slide {slide.slide_number} uses VISUAL_ANCHOR with no explanatory body; add cards with points or a callout_box."
            )

        if slide.layout_type == "DUAL_PILLARS" and _dual_pillars_should_be_richer(slide):
            issues.append(
                f"Slide {slide.slide_number} uses DUAL_PILLARS for a multi-branch topic; use COMPARISON_TABLE, ICON_GRID, PROCESS_TIMELINE, or add card points."
            )
            break

    missing_topics = _missing_coverage_topics(deck, coverage_topics or [])
    if missing_topics:
        issues.append("Missing important source topics: " + ", ".join(missing_topics[:5]) + ".")

    return issues


def _has_component_anchor(slide: SlidePayload) -> bool:
    components = slide.components
    if components.visual_anchor.kind != "none":
        return True
    if any(card.icon_key in ICON_KEYS for card in components.cards):
        return True
    if any(metric.icon_key in ICON_KEYS for metric in components.metrics):
        return True
    if any(row.icon_key in ICON_KEYS for row in components.comparison):
        return True
    if any(item.icon_key in ICON_KEYS for item in components.checklist):
        return True
    if slide.layout_type == "PROCESS_TIMELINE" and components.flow_steps:
        return True
    return False


def _consecutive_layout_issue(slides: list[SlidePayload]) -> str | None:
    previous_layout = ""
    repeat_count = 0
    for slide in slides:
        if slide.layout_type == previous_layout:
            repeat_count += 1
            if repeat_count > 2:
                return (
                    f"Slides around {slide.slide_number} repeat {slide.layout_type} more than two times consecutively; "
                    "switch one slide to PROCESS_TIMELINE, COMPARISON_TABLE, ICON_GRID, VISUAL_ANCHOR, or TRANSITION."
                )
        else:
            previous_layout = slide.layout_type
            repeat_count = 1
    return None


def _is_generic_slide_title(title: str) -> bool:
    normalized = _normalized_label(title)
    if normalized in GENERIC_SLIDE_TITLES:
        return True
    words = normalized.split()
    return len(words) <= 2 and any(word in GENERIC_SLIDE_TITLES for word in words)


def _is_generic_deck_title(title: str) -> bool:
    normalized = _normalized_label(title)
    if not normalized:
        return True
    return _is_generic_slide_title(title) or normalized.startswith(("academic overview", "tong quan hoc thuat"))


def _is_empty_visual_anchor_slide(slide: SlidePayload) -> bool:
    if slide.layout_type != "VISUAL_ANCHOR":
        return False
    components = slide.components
    if components.callout_box and components.callout_box.text.strip():
        return False
    if slide.bullets:
        return False
    for card in components.cards:
        if card.desc.strip() or any(point.strip() for point in card.points):
            return False
    if components.checklist or components.metrics or components.comparison or components.flow_steps:
        return False
    return True


def _fill_empty_visual_anchor_fallbacks(deck: SlideDeckPayload) -> None:
    """Keep accepted fallback decks from producing blank VISUAL_ANCHOR pages."""
    for slide in deck.slides:
        if not _is_empty_visual_anchor_slide(slide):
            continue
        fallback_text = slide.components.visual_anchor.caption or slide.subtitle or slide.title
        slide.components.callout_box = CalloutBox(
            type="INSIGHT",
            text=_truncate_words(str(fallback_text), CALLOUT_MAX_WORDS),
        )


def _is_sparse_slide(slide: SlidePayload) -> bool:
    if slide.layout_type not in {"DUAL_PILLARS", "GRID_COMPOSITE", "VISUAL_ANCHOR", "ICON_GRID"}:
        return False
    if slide.visual.kind in {"source_page", "generated_image"} or slide.components.visual_anchor.kind in {"source_page", "generated_image"}:
        return False
    visible_words = _slide_visible_word_count(slide.model_dump())
    card_points = sum(len(card.points) for card in slide.components.cards)
    if slide.layout_type == "VISUAL_ANCHOR":
        return visible_words < 45 and card_points == 0
    if slide.layout_type == "ICON_GRID":
        return visible_words < 75 or card_points < 4
    return visible_words < 60 or (slide.components.cards and card_points == 0 and visible_words < 70)


def _dual_pillars_should_be_richer(slide: SlidePayload) -> bool:
    card_points = sum(len(card.points) for card in slide.components.cards)
    if card_points:
        return False
    text = " ".join(_visible_strings(slide.model_dump()))
    branch_markers = len(re.findall(r"[,/;]| and | va | và |\\+", _normalized_label(text)))
    return branch_markers >= 3


def _missing_coverage_topics(deck: SlideDeckPayload, coverage_topics: list[str]) -> list[str]:
    if not coverage_topics:
        return []
    deck_text = " ".join(_visible_strings(deck.model_dump()))
    missing: list[str] = []
    for topic in coverage_topics:
        score = _topic_match_score(topic, deck_text)
        if score < _coverage_presence_threshold(topic):
            missing.append(topic)
    return missing


def _coverage_presence_threshold(topic: str) -> int:
    if topic in {"Smart Strings", "Pseudo Localization", "Object Pooling", "Pre-flight Checklist"}:
        return 1
    return 2


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
        "resolve",
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
