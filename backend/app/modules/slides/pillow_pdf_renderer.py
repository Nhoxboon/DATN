"""Pillow-based raster PDF rendering for slide decks."""

from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.modules.slides.browser_pdf_renderer import render_deck_pdf_with_browser
from app.modules.slides.component_utils import (
    _component_anchor,
    _component_callout,
    _component_cards,
    _component_checklist,
    _component_comparison,
    _component_flow_steps,
    _component_metrics,
    _visual_anchor_points,
)
from app.modules.slides.constants import CARD_MAX_POINTS, ICON_LABELS, PDF_RENDER_SCALE, SLIDE_HEIGHT, SLIDE_WIDTH
from app.modules.slides.text_utils import _visible_strings


logger = logging.getLogger(__name__)

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
            logger.info(
                "Browser slide PDF render failed attempt=%s/%s error=%s",
                attempt + 1,
                max_retries + 1,
                exc,
                exc_info=logger.isEnabledFor(logging.DEBUG),
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
