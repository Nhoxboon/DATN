"""Tests for notebook-scoped Gemini cache registry keys."""

from __future__ import annotations

from fnmatch import fnmatch
import unittest
from unittest.mock import patch

from app.services.rag.cache_registry import (
    build_document_cache_key,
    build_document_cache_manifest_key,
    get_cache_manifest,
    get_cache_name,
    invalidate_document_caches,
    set_cache_manifest,
    set_cache_name,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def setex(self, key: str, _ttl_seconds: int, value: str) -> None:
        self.values[str(key)] = value

    def get(self, key: str) -> str | None:
        return self.values.get(str(key))

    def delete(self, key: str) -> int:
        key_str = str(key)
        if key_str in self.values:
            del self.values[key_str]
            return 1
        return 0

    def keys(self, pattern: str) -> list[str]:
        return [key for key in self.values if fnmatch(key, pattern)]

    def scan_iter(self, match: str | None = None):
        for key in list(self.values):
            if match is None or fnmatch(key, match):
                yield key


class CacheRegistryTests(unittest.TestCase):
    def test_cache_key_includes_notebook_scope(self) -> None:
        key_a = build_document_cache_key("notebook-a", ["Design Notes"])
        key_b = build_document_cache_key("notebook-b", ["Design Notes"])

        self.assertNotEqual(key_a, key_b)
        self.assertTrue(key_a.startswith("gemini_cache:notebook-a:docs:"))
        self.assertTrue(key_b.startswith("gemini_cache:notebook-b:docs:"))

    def test_cache_key_sorts_and_encodes_document_names(self) -> None:
        key = build_document_cache_key("note/1", ["B File", "A|File", "B File"])

        self.assertEqual(key, "gemini_cache:note%2F1:docs:A%7CFile|B%20File")

    def test_cache_manifest_uses_matching_scoped_key(self) -> None:
        redis = FakeRedis()
        manifest_key = build_document_cache_manifest_key("note/1", ["B File", "A|File"])
        sources = [{"document": "A|File", "page_range": "1-2"}]

        with patch("app.services.rag.cache_registry.get_redis_client", return_value=redis):
            set_cache_manifest(manifest_key, sources)

            self.assertEqual(manifest_key, "gemini_cache_manifest:note%2F1:docs:A%7CFile|B%20File")
            self.assertEqual(get_cache_manifest(manifest_key), sources)

    def test_invalidate_document_caches_removes_matching_notebook_doc_sets_only(self) -> None:
        redis = FakeRedis()
        key_single = build_document_cache_key("notebook-1", ["doc-a"])
        key_combo = build_document_cache_key("notebook-1", ["doc-a", "doc-b"])
        key_other_doc = build_document_cache_key("notebook-1", ["doc-b"])
        key_other_notebook = build_document_cache_key("notebook-2", ["doc-a"])
        manifest_single = build_document_cache_manifest_key("notebook-1", ["doc-a"])
        manifest_combo = build_document_cache_manifest_key("notebook-1", ["doc-a", "doc-b"])
        manifest_other_doc = build_document_cache_manifest_key("notebook-1", ["doc-b"])
        manifest_other_notebook = build_document_cache_manifest_key("notebook-2", ["doc-a"])

        with patch("app.services.rag.cache_registry.get_redis_client", return_value=redis):
            set_cache_name(key_single, "cache-single")
            set_cache_name(key_combo, "cache-combo")
            set_cache_name(key_other_doc, "cache-other-doc")
            set_cache_name(key_other_notebook, "cache-other-notebook")
            set_cache_manifest(manifest_single, [{"document": "doc-a"}])
            set_cache_manifest(manifest_combo, [{"document": "doc-a"}, {"document": "doc-b"}])
            set_cache_manifest(manifest_other_doc, [{"document": "doc-b"}])
            set_cache_manifest(manifest_other_notebook, [{"document": "doc-a"}])

            deleted = invalidate_document_caches("notebook-1", "doc-a")

            self.assertEqual(deleted, 4)
            self.assertIsNone(get_cache_name(key_single))
            self.assertIsNone(get_cache_name(key_combo))
            self.assertIsNone(get_cache_manifest(manifest_single))
            self.assertIsNone(get_cache_manifest(manifest_combo))
            self.assertEqual(get_cache_name(key_other_doc), "cache-other-doc")
            self.assertEqual(get_cache_name(key_other_notebook), "cache-other-notebook")
            self.assertEqual(get_cache_manifest(manifest_other_doc), [{"document": "doc-b"}])
            self.assertEqual(get_cache_manifest(manifest_other_notebook), [{"document": "doc-a"}])


if __name__ == "__main__":
    unittest.main()
