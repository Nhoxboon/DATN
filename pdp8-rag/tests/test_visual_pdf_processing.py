"""Tests for image-aware PDF text normalization and chunk metadata."""

from PIL import Image

from app.services.pdf_processor.processor import PDFProcessor


class DummyChunk:
    """Minimal chunk object matching the chonkie fields used by PDFProcessor."""

    def __init__(self, text: str):
        self.text = text
        self.start_index = 0
        self.end_index = len(text)
        self.token_count = len(text.split())


class DummyChunker:
    """Single-chunk test double to avoid external embedding calls."""

    def chunk(self, text: str):
        return [DummyChunk(text)]


def make_processor() -> PDFProcessor:
    processor = PDFProcessor.__new__(PDFProcessor)
    processor.chunker = DummyChunker()
    processor.caption_client = None
    processor.image_caption_model = "fake-model"
    return processor


class FakeCaptionModels:
    def generate_content(self, **kwargs):
        class Response:
            text = "A state machine diagram with Idle, Running, and Failed states connected by transition arrows."

        return Response()


class FakeCaptionClient:
    models = FakeCaptionModels()


def test_marker_visual_description_is_normalized_with_page_number():
    processor = make_processor()

    markdown = (
        "Before\n"
        "Image /page/1/Figure/3 description: A chart shows 42 MW of solar capacity.\n"
        "After"
    )

    normalized = processor._normalize_visual_descriptions(markdown)

    assert "Figure description on page 2: A chart shows 42 MW of solar capacity." in normalized


def test_visual_description_chunk_metadata_is_set():
    processor = make_processor()
    text = (
        "Section text\n"
        "Figure description on page 2: A chart shows 42 MW of solar capacity.\n"
        "More section text"
    )

    chunks = processor.chunk_text_with_pages(text, {"total_pages": 2})

    assert len(chunks) == 1
    assert chunks[0]["has_visual"] is True
    assert chunks[0]["visual_pages"] == [2]
    assert chunks[0]["content_type"] == "mixed"


def test_markdown_image_placeholder_is_replaced_with_caption():
    processor = make_processor()
    processor.caption_client = FakeCaptionClient()
    image = Image.new("RGB", (32, 32), color="white")

    markdown = "Please inspect this:\n\n![](_page_0_Figure_0.jpeg)\n"
    replaced = processor._replace_image_placeholders_with_captions(
        markdown,
        {"_page_0_Figure_0.jpeg": image},
    )

    assert "![](_page_0_Figure_0.jpeg)" not in replaced
    assert "Figure description on page 1:" in replaced
    assert "Idle, Running, and Failed states" in replaced


def test_markdown_image_placeholder_uses_page_render_fallback_when_image_missing():
    processor = make_processor()
    processor.caption_client = FakeCaptionClient()
    processor._render_pdf_page_for_caption = lambda file_path, page_number: Image.new("RGB", (32, 32), color="white")

    markdown = "Please inspect this:\n\n![](_page_0_Figure_0.jpeg)\n"
    replaced = processor._replace_image_placeholders_with_captions(
        markdown,
        {},
        "example.pdf",
    )

    assert "![](_page_0_Figure_0.jpeg)" not in replaced
    assert "Figure description on page 1:" in replaced


def test_markdown_image_placeholder_is_not_kept_when_caption_fails():
    processor = make_processor()
    processor._render_pdf_page_for_caption = lambda file_path, page_number: Image.new("RGB", (32, 32), color="white")

    markdown = "Please inspect this:\n\n![](_page_0_Figure_0.jpeg)\n"
    replaced = processor._replace_image_placeholders_with_captions(
        markdown,
        {},
        "example.pdf",
    )

    assert "![](_page_0_Figure_0.jpeg)" not in replaced
    assert "Visual caption generation failed" in replaced
