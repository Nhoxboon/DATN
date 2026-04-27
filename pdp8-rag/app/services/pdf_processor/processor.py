"""PDF processing service using marker with LLM hybrid mode."""

import io
import re
from pathlib import Path
from typing import Dict, Any, List
from google import genai
from google.genai import types
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from chonkie.chunker.semantic import SemanticChunker
from app.services.embedding.service import EmbeddingService
from app.core.config import AppConfig, Settings


class PDFProcessor:
    """Process PDF documents using marker with LLM hybrid mode."""

    VISUAL_DESCRIPTION_PATTERN = re.compile(
        r"\b(?:image|figure|picture)(?:/figure)?(?:\s+[^:\n]{0,160})?\s+description"
        r"(?:\s+on\s+page\s+\d+)?\s*:",
        re.IGNORECASE,
    )
    MARKER_VISUAL_DESCRIPTION_LINE = re.compile(
        r"^\s*(?P<label>image|figure|picture)\s+"
        r"(?P<block_id>/page/(?P<page>\d+)/(?P<block_type>Picture|Figure)/[^:]+|[^:]+?)"
        r"\s+description:\s*(?P<description>.+?)\s*$",
        re.IGNORECASE,
    )
    VISUAL_PAGE_PATTERN = re.compile(
        r"\b(?:image|figure|picture)(?:/figure)?\s+description\s+on\s+page\s+(\d+)\s*:",
        re.IGNORECASE,
    )
    MARKDOWN_IMAGE_PATTERN = re.compile(
        r"!\[(?P<alt>[^\]]*)\]\((?P<path>[^)]+)\)"
    )
    IMAGE_FILENAME_PAGE_PATTERN = re.compile(r"(?:^|_)page[_-](?P<page>\d+)", re.IGNORECASE)
    IMAGE_FILENAME_KIND_PATTERN = re.compile(r"(?P<kind>figure|picture|image)", re.IGNORECASE)

    def __init__(self, app_config: AppConfig, settings: Settings, embedding_service: EmbeddingService):
        """
        Initialize PDF processor with config.

        Args:
            app_config: Application configuration
            settings: Environment settings
            embedding_service: Embedding service instance
        """
        pdf_config = app_config.pdf
        chunking_config = app_config.chunking

        describe_images = getattr(pdf_config, "describe_images", False)
        caption_model = getattr(pdf_config, "image_caption_model", None) or pdf_config.llm_model

        # Configure marker with LLM support and table extraction.
        # Keep image extraction enabled so placeholders such as
        config = {
            "output_format": "markdown",
            "use_llm": pdf_config.use_llm or describe_images,
            "llm_model": pdf_config.llm_model,
            "gemini_model_name": caption_model,
            "gemini_api_key": settings.google_api_key,
            "extract_tables": True,
        }
        if describe_images:
            config["extract_images"] = True

        self.describe_images = describe_images
        self.image_caption_model = caption_model
        self.caption_client = genai.Client(api_key=settings.google_api_key) if describe_images else None

        self.config_parser = ConfigParser(config)
        self.converter = PdfConverter(
            config=self.config_parser.generate_config_dict(),
            artifact_dict=create_model_dict(),
            processor_list=self.config_parser.get_processors(),
            renderer=self.config_parser.get_renderer(),
            llm_service=self.config_parser.get_llm_service()
        )

        # Initialize semantic chunker with embedding service
        self.embedding_service = embedding_service
        self.chunker = SemanticChunker(
            embedding_function=self.embedding_service.embed_text,
            chunk_size=chunking_config.chunk_size,
            threshold=chunking_config.similarity_threshold,
            min_sentences_per_chunk=3, 
            min_characters_per_sentence=30 
        )

    def process_pdf(self, file_path: str) -> tuple[str, Dict[str, Any]]:
        """
        Process a PDF file and extract markdown content with metadata.

        Args:
            file_path: Path to the PDF file

        Returns:
            Tuple of (markdown string, metadata dict with page info)
        """
        if not Path(file_path).exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        rendered = self.converter(file_path)
        markdown = rendered.markdown
        images = rendered.images if hasattr(rendered, "images") else {}
        if self.describe_images:
            markdown = self._normalize_visual_descriptions(markdown)
            markdown = self._replace_image_placeholders_with_captions(markdown, images, file_path)

        rendered_metadata = getattr(rendered, "metadata", {}) or {}
        page_stats = (
            rendered_metadata.get("page_stats", [])
            if isinstance(rendered_metadata, dict)
            else []
        )
        metadata = {
            "total_pages": len(page_stats) if page_stats else (
                len(rendered.pages) if hasattr(rendered, "pages") else None
            ),
            "images": images,
            "image_count": len(images) if hasattr(images, "__len__") else 0,
            "image_ids": [str(image_id) for image_id in images.keys()] if isinstance(images, dict) else [],
            "marker_metadata": rendered_metadata,
            "describe_images": self.describe_images,
        }

        return markdown, metadata

    def chunk_text_with_pages(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split text into semantic chunks, preserving page numbers and tables.

        Args:
            text: Text from PDF
            metadata: Metadata from PDF processing

        Returns:
            List of text chunks with metadata including page numbers
        """
        # Preprocess to protect tables from being split
        protected_text, table_markers = self._protect_tables(text)

        chunks_result = self.chunker.chunk(protected_text)
        page_boundaries = self._extract_page_boundaries(text)

        chunks = []
        for idx, chunk in enumerate(chunks_result):
            # Restore tables in chunk text
            chunk_text = self._restore_tables(chunk.text, table_markers)

            chunk_pages = self._get_chunk_pages(
                chunk.start_index,
                chunk.end_index,
                page_boundaries
            )

            # Check if chunk contains a table or visual description.
            has_table = self._contains_table(chunk_text)
            has_visual = self._contains_visual_description(chunk_text)
            visual_pages = self._extract_visual_pages(chunk_text)
            content_type = self._classify_content_type(chunk_text, has_visual)

            chunks.append({
                "text": chunk_text,
                "chunk_id": idx,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
                "token_count": chunk.token_count,
                "pages": chunk_pages,
                "page_range": f"{min(chunk_pages)}-{max(chunk_pages)}" if chunk_pages else "unknown",
                "has_table": has_table,
                "has_visual": has_visual,
                "visual_pages": visual_pages,
                "content_type": content_type
            })

        return chunks

    def _normalize_visual_descriptions(self, markdown: str) -> str:
        """
        Convert Marker image description lines into stable, searchable text.

        Marker emits lines like "Image /page/0/Picture/1 description: ...".
        Keeping the page in human numbering makes the chunk useful both for
        retrieval and for citations shown to the user.
        """
        normalized_lines = []

        for line in markdown.splitlines():
            match = self.MARKER_VISUAL_DESCRIPTION_LINE.match(line)
            if not match:
                normalized_lines.append(line)
                continue

            block_type = (match.group("block_type") or match.group("label") or "image").lower()
            label = "Figure" if block_type == "figure" else "Image"
            page = match.group("page")
            description = match.group("description").strip()

            if page is not None:
                page_number = int(page) + 1
                normalized_lines.append(f"{label} description on page {page_number}: {description}")
            else:
                normalized_lines.append(f"{label} description: {description}")

        return "\n".join(normalized_lines)

    def _replace_image_placeholders_with_captions(
        self,
        markdown: str,
        images: Any,
        file_path: str | None = None
    ) -> str:
        """
        Replace markdown image placeholders with Gemini-generated descriptions.

        Some Marker outputs keep visuals as `![](_page_0_Figure_0.jpeg)` even
        when LLM processing is enabled. Those placeholders are useless to RAG,
        so this fallback textualizes any image that Marker returned separately.
        """
        if not self.MARKDOWN_IMAGE_PATTERN.search(markdown):
            return markdown

        image_lookup = self._build_image_lookup(images)

        def replace(match: re.Match[str]) -> str:
            image_path = match.group("path").strip()
            image = self._find_rendered_image(image_path, image_lookup)
            page_number = self._page_number_from_image_path(image_path)
            if image is None and page_number is not None and file_path:
                image = self._render_pdf_page_for_caption(file_path, page_number)
            if image is None:
                return match.group(0)

            label = self._label_from_image_path(image_path)
            description = self._describe_rendered_image(image_path, image, page_number)
            if not description:
                return self._visual_caption_failure_text(image_path, label, page_number)

            if page_number is not None:
                return f"{label} description on page {page_number}: {description}"
            return f"{label} description: {description}"

        return self.MARKDOWN_IMAGE_PATTERN.sub(replace, markdown)

    def _render_pdf_page_for_caption(self, file_path: str, page_number: int) -> Any:
        """Render a one-based PDF page when Marker did not return a crop."""
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(file_path)
            page = pdf[page_number - 1]
            bitmap = page.render(scale=2)
            return bitmap.to_pil()
        except Exception as e:
            print(f"Warning: Could not render page {page_number} for image captioning: {e}")
            return None

    def _build_image_lookup(self, images: Any) -> Dict[str, Any]:
        """Build a tolerant lookup for Marker-rendered images."""
        if not isinstance(images, dict):
            return {}

        lookup = {}
        for key, image in images.items():
            key_text = str(key)
            lookup[key_text] = image
            lookup[Path(key_text).name] = image

        return lookup

    def _find_rendered_image(self, image_path: str, image_lookup: Dict[str, Any]) -> Any:
        """Find the PIL image object for a markdown image path."""
        path = image_path.strip()
        candidates = [
            path,
            Path(path).name,
            path.lstrip("./"),
            Path(path.lstrip("./")).name,
        ]

        for candidate in candidates:
            if candidate in image_lookup:
                return image_lookup[candidate]

        return None

    def _page_number_from_image_path(self, image_path: str) -> int | None:
        """Extract a one-based page number from Marker image filenames."""
        match = self.IMAGE_FILENAME_PAGE_PATTERN.search(Path(image_path).name)
        if not match:
            return None
        return int(match.group("page")) + 1

    def _label_from_image_path(self, image_path: str) -> str:
        """Return a readable visual label from Marker image filenames."""
        match = self.IMAGE_FILENAME_KIND_PATTERN.search(Path(image_path).name)
        if not match:
            return "Image"

        kind = match.group("kind").lower()
        return "Figure" if kind == "figure" else "Image"

    def _describe_rendered_image(self, image_path: str, image: Any, page_number: int | None) -> str:
        """Generate a searchable description for one rendered image."""
        if self.caption_client is None:
            return ""

        try:
            image_copy = image.copy()
            image_copy.thumbnail((1600, 1600))
            if image_copy.mode != "RGB":
                image_copy = image_copy.convert("RGB")

            image_bytes = io.BytesIO()
            image_copy.save(image_bytes, format="WEBP")
            image_part = types.Part.from_bytes(
                data=image_bytes.getvalue(),
                mime_type="image/webp"
            )

            page_hint = f" on page {page_number}" if page_number is not None else ""
            prompt = (
                "Create a faithful, searchable description of this document visual"
                f"{page_hint}. If it contains readable text, transcribe the important text. "
                "If it is a diagram, describe the nodes/states, arrows/transitions, and overall flow. "
                "If it is a chart or table-like visual, include labels, numbers, axes, and relationships. "
                f"Source image filename: {Path(image_path).name}."
            )

            response = self.caption_client.models.generate_content(
                model=self.image_caption_model,
                contents=[image_part, prompt],
                config=types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1200,
                ),
            )

            return (response.text or "").strip()
        except Exception as e:
            print(f"Warning: Could not describe image placeholder '{image_path}': {e}")
            return ""

    def _visual_caption_failure_text(
        self,
        image_path: str,
        label: str,
        page_number: int | None
    ) -> str:
        """Return diagnostic text instead of silently storing raw markdown image syntax."""
        page_text = f" on page {page_number}" if page_number is not None else ""
        return (
            f"{label} description{page_text}: Visual caption generation failed for "
            f"{Path(image_path).name}. Check GOOGLE_API_KEY, Gemini vision access, "
            "and backend/worker logs before re-indexing this document."
        )

    def _extract_page_boundaries(self, text: str) -> List[int]:
        """Extract character positions of page boundaries from markdown."""
        boundaries = [0]
        lines = text.split('\n')
        current_pos = 0

        for line in lines:
            if '---' in line or 'Page ' in line:
                boundaries.append(current_pos)
            current_pos += len(line) + 1

        return boundaries

    def _get_chunk_pages(self, start_idx: int, end_idx: int, page_boundaries: List[int]) -> List[int]:
        """Determine which pages a chunk spans."""
        pages = []

        for i, boundary in enumerate(page_boundaries):
            if i + 1 < len(page_boundaries):
                next_boundary = page_boundaries[i + 1]
                if start_idx < next_boundary and end_idx > boundary:
                    pages.append(i + 1)
            else:
                if start_idx >= boundary:
                    pages.append(i + 1)

        return pages if pages else [1]

    def _protect_tables(self, text: str) -> tuple[str, Dict[str, str]]:
        """
        Replace markdown tables with placeholders to prevent splitting.

        Returns:
            Tuple of (protected text, dict of placeholders to original tables)
        """
        import re

        table_markers = {}
        protected_text = text

        # Find markdown tables (lines with | characters)
        table_pattern = r'(\|[^\n]+\|\n)+(\|[-:| ]+\|\n)?(\|[^\n]+\|\n)+'
        tables = re.finditer(table_pattern, text)

        for idx, match in enumerate(tables):
            table_text = match.group(0)
            marker = f"<<<TABLE_{idx}>>>"
            table_markers[marker] = table_text
            protected_text = protected_text.replace(table_text, marker, 1)

        return protected_text, table_markers

    def _restore_tables(self, text: str, table_markers: Dict[str, str]) -> str:
        """Restore original tables from placeholders."""
        restored_text = text
        for marker, table in table_markers.items():
            restored_text = restored_text.replace(marker, table)
        return restored_text

    def _contains_table(self, text: str) -> bool:
        """Check if text contains a markdown table."""
        import re
        # Check for markdown table pattern
        table_pattern = r'\|[^\n]+\|'
        return bool(re.search(table_pattern, text))

    def _contains_visual_description(self, text: str) -> bool:
        """Check if text contains a generated image or figure description."""
        return bool(self.VISUAL_DESCRIPTION_PATTERN.search(text))

    def _extract_visual_pages(self, text: str) -> List[int]:
        """Extract page numbers mentioned by generated image descriptions."""
        return [
            int(page)
            for page in self.VISUAL_PAGE_PATTERN.findall(text)
        ]

    def _classify_content_type(self, text: str, has_visual: bool) -> str:
        """Classify a chunk for downstream source display and debugging."""
        if not has_visual:
            return "text"

        meaningful_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if meaningful_lines and all(
            self.VISUAL_DESCRIPTION_PATTERN.search(line)
            for line in meaningful_lines
        ):
            return "visual_description"

        return "mixed"
