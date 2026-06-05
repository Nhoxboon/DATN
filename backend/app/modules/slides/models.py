"""Internal Pydantic models for slide deck generation."""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.slides.constants import (
    CALLOUT_MAX_WORDS,
    CARD_DESC_MAX_WORDS,
    CARD_MAX_POINTS,
    CARD_POINT_MAX_WORDS,
    CITATION_PATTERN,
    FINAL_SUMMARY_TITLES,
    FLOW_ACTION_MAX_WORDS,
    MAX_BULLETS_PER_SLIDE,
    MAX_SLIDES,
    MAX_SOURCE_CROPS_PER_DECK,
    MAX_WORDS_PER_BULLET,
    MIN_SLIDES,
    VISUAL_LAYOUTS,
)
from app.modules.slides.text_utils import (
    _looks_action_like,
    _normalized_label,
    _visible_strings,
    _word_count,
)

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
