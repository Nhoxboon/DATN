"""Tests for RAG citation rewriting against cached source manifests."""

from __future__ import annotations

import unittest

from app.services.rag.service import RAGService


class RAGCitationTests(unittest.TestCase):
    def test_manifest_citations_are_compacted_to_returned_sources(self) -> None:
        manifest = [
            {"document": "doc-a", "page_range": "1"},
            {"document": "doc-b", "page_range": "2"},
            {"document": "doc-c", "page_range": "3"},
        ]

        resolved = RAGService._resolve_manifest_citations("Use C [3] and A [1, 3].", manifest)

        self.assertIsNotNone(resolved)
        assert resolved is not None
        answer, sources = resolved
        self.assertEqual(answer, "Use C [1] and A [2, 1].")
        self.assertEqual(sources, [manifest[2], manifest[0]])

    def test_manifest_citations_reject_out_of_range_source_numbers(self) -> None:
        manifest = [{"document": "doc-a", "page_range": "1"}]

        resolved = RAGService._resolve_manifest_citations("Missing source [2].", manifest)

        self.assertIsNone(resolved)

    def test_manifest_citations_reject_answers_without_citations(self) -> None:
        manifest = [{"document": "doc-a", "page_range": "1"}]

        resolved = RAGService._resolve_manifest_citations("No citation here.", manifest)

        self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
