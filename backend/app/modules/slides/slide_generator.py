"""LLM outline and deck generation helpers for slide decks."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.modules.slides.constants import (
    BATCH_CONTEXT_CHARS,
    CALLOUT_MAX_WORDS,
    CARD_DESC_MAX_WORDS,
    CARD_MAX_POINTS,
    CARD_POINT_MAX_WORDS,
    FLOW_ACTION_MAX_WORDS,
    ICON_KEYS,
    MAX_DECK_ATTEMPTS,
    MAX_DECK_OUTPUT_TOKENS,
    MAX_SLIDES,
    MIN_SLIDES,
)
from app.modules.slides.coverage_utils import (
    _expected_coverage_topics,
    _topic_match_score,
    _topic_tokens,
)
from app.modules.slides.models import CoverageItem, SlideDeckPayload, StoryOutlinePayload
from app.modules.slides.payload_utils import (
    _fill_empty_visual_anchor_fallbacks,
    _is_generic_deck_title,
    _parsed_response_payload,
    _repair_deck_payload,
    _review_deck_design,
)
from app.modules.slides.text_utils import _looks_vietnamese, _normalized_label, _split_text


logger = logging.getLogger(__name__)


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
