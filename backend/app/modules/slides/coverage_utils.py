"""Coverage-topic detection helpers for slide deck generation."""

from __future__ import annotations

from app.modules.slides.constants import COVERAGE_TOPIC_RULES
from app.modules.slides.text_utils import _normalized_label


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
