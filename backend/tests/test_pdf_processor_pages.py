"""Tests for preserving PDF page metadata during chunking."""

from __future__ import annotations

import unittest

from app.services.pdf_processor.processor import PDFProcessor


class PDFProcessorPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.processor = object.__new__(PDFProcessor)

    def test_extract_page_boundaries_from_marker_pagination(self) -> None:
        text = "\n\n{0}------------------------------------------------\n\nPage one text\n\n{1}------------------------------------------------\n\nPage two text"

        boundaries = self.processor._extract_page_boundaries(text, {"total_pages": 2})

        self.assertEqual(boundaries, [(54, 1), (122, 2)])

    def test_get_chunk_pages_uses_marker_page_numbers(self) -> None:
        boundaries = [(10, 1), (50, 2), (100, 3)]

        self.assertEqual(self.processor._get_chunk_pages(55, 75, boundaries), [2])
        self.assertEqual(self.processor._get_chunk_pages(45, 105, boundaries), [1, 2, 3])

    def test_strip_page_markers_removes_marker_from_stored_chunk_text(self) -> None:
        text = "{0}------------------------------------------------\n\nActual content"

        self.assertEqual(self.processor._strip_page_markers(text), "Actual content")

    def test_fallback_distributes_pages_when_marker_is_missing(self) -> None:
        text = "a" * 100

        boundaries = self.processor._extract_page_boundaries(text, {"total_pages": 4})

        self.assertEqual(boundaries, [(0, 1), (25, 2), (50, 3), (75, 4)])

    def test_markdown_table_separator_is_not_treated_as_page_boundary(self) -> None:
        text = "| A | B |\n|---|---|\n| 1 | 2 |"

        boundaries = self.processor._extract_page_boundaries(text, {"total_pages": 1})

        self.assertEqual(boundaries, [(0, 1)])

    def test_visual_caption_validator_strips_completion_marker(self) -> None:
        text = (
            "A complete diagram description with states and transitions.\n"
            f"{PDFProcessor.VISUAL_CAPTION_COMPLETE_MARKER}"
        )

        caption = self.processor._validated_visual_caption_text(
            text,
            "_page_0_Figure_0.jpeg",
            "STOP",
        )

        self.assertEqual(caption, "A complete diagram description with states and transitions.")

    def test_visual_caption_validator_rejects_missing_completion_marker(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing completion marker"):
            self.processor._validated_visual_caption_text(
                "Figure description on page 1: This diagram is organized into Ability, Grounded, and",
                "_page_0_Figure_0.jpeg",
                "STOP",
            )

    def test_visual_caption_validator_rejects_dangling_ending(self) -> None:
        text = (
            "Figure description on page 1: This diagram is organized into Ability, Grounded, and\n"
            f"{PDFProcessor.VISUAL_CAPTION_COMPLETE_MARKER}"
        )

        with self.assertRaisesRegex(ValueError, "dangling ending"):
            self.processor._validated_visual_caption_text(
                text,
                "_page_0_Figure_0.jpeg",
                "STOP",
            )


if __name__ == "__main__":
    unittest.main()
