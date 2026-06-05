"""Payload parsing, repair, and design-review helpers for slide decks."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from pydantic import BaseModel

from app.modules.slides.constants import (
    CALLOUT_MAX_WORDS,
    CARD_DESC_MAX_WORDS,
    CARD_MAX_POINTS,
    CARD_POINT_MAX_WORDS,
    COMPONENT_LAYOUTS,
    FLOW_ACTION_MAX_WORDS,
    GENERIC_SLIDE_TITLES,
    ICON_KEYS,
    VISUAL_LAYOUTS,
)
from app.modules.slides.coverage_utils import _topic_match_score
from app.modules.slides.models import CalloutBox, SlideDeckPayload, SlidePayload
from app.modules.slides.text_utils import (
    _looks_action_like,
    _normalize_flow_step_marker,
    _normalized_label,
    _truncate_words,
    _visible_strings,
    _word_count,
)


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
