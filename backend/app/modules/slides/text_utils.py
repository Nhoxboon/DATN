"""Text normalization helpers for slide deck generation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.modules.slides.constants import DANGLING_TRAILING_WORDS

def _looks_vietnamese(text: str) -> bool:
    normalized = text.casefold()
    return bool(re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", normalized)) or any(
        marker in normalized for marker in (" và ", " của ", " không ", " trong ", " được ")
    )


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


def _split_text(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
