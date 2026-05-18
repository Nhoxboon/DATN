"""Helpers for user-facing document names and safe storage paths."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path


_CLIENT_PATH_SEPARATOR = re.compile(r"[\\/]+")
_UNSAFE_STORAGE_CHARS = re.compile(r"[^A-Za-z0-9]+")
SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


def client_filename(filename: str) -> str:
    """Return only the filename component from a browser-provided path."""
    return _CLIENT_PATH_SEPARATOR.split(filename.strip())[-1].strip()


def validate_pdf_filename(filename: str) -> str:
    """Validate and return a clean PDF filename."""
    clean_filename = client_filename(filename)

    if not clean_filename:
        raise ValueError("Filename is required")

    if Path(clean_filename).suffix.lower() != ".pdf":
        raise ValueError("Only PDF files are supported")

    return clean_filename


def validate_document_filename(filename: str) -> str:
    """Validate and return a clean supported document filename."""
    clean_filename = client_filename(filename)

    if not clean_filename:
        raise ValueError("Filename is required")

    if document_extension_from_filename(clean_filename) not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError("Only PDF and DOCX files are supported")

    return clean_filename


def document_extension_from_filename(filename: str) -> str:
    """Return the lowercase extension for a client-provided filename."""
    return Path(client_filename(filename)).suffix.lower()


def document_name_from_filename(filename: str) -> str:
    """Build the user-facing document name from a supported filename."""
    clean_filename = validate_document_filename(filename)
    document_name = Path(clean_filename).stem.strip()

    return normalize_document_name(document_name)


def normalize_document_name(document_name: str) -> str:
    """Normalize whitespace around a user-facing document name."""
    clean_document_name = document_name.strip()

    if not clean_document_name:
        raise ValueError("Document name is required")

    return clean_document_name


def safe_pdf_storage_path(document_name: str) -> str:
    """Return an ASCII-only, collision-resistant storage object path."""
    return safe_document_storage_path(document_name, ".pdf")


def safe_document_storage_path(document_name: str, extension: str) -> str:
    """Return an ASCII-only, collision-resistant storage path with an extension."""
    clean_document_name = normalize_document_name(document_name)
    slug = _ascii_slug(clean_document_name)
    digest = hashlib.sha1(clean_document_name.encode("utf-8")).hexdigest()[:10]
    clean_extension = extension.lower()
    if clean_extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError("Unsupported document extension")

    return f"{slug}-{digest}{clean_extension}"


def _ascii_slug(value: str) -> str:
    without_d = value.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", without_d)
    ascii_text = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    slug = _UNSAFE_STORAGE_CHARS.sub("-", ascii_text).strip("-")

    return slug or "document"
