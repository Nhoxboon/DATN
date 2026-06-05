"""Component access helpers shared by slide validators and renderers."""

from __future__ import annotations

from typing import Any

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
