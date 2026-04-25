"""PDF processing service using marker with LLM hybrid mode."""

from pathlib import Path
from typing import Dict, Any, List
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.config.parser import ConfigParser
from chonkie.chunker.semantic import SemanticChunker
from app.services.embedding.service import EmbeddingService
from app.core.config import AppConfig, Settings


class PDFProcessor:
    """Process PDF documents using marker with LLM hybrid mode."""

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

        # Configure marker with LLM support and table extraction
        config = {
            "output_format": "markdown",
            "use_llm": pdf_config.use_llm,
            "llm_model": pdf_config.llm_model,
            "gemini_api_key": settings.google_api_key,
            "extract_tables": True,
        }

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

        metadata = {
            "total_pages": len(rendered.pages) if hasattr(rendered, "pages") else None,
            "images": rendered.images if hasattr(rendered, "images") else [],
        }

        return rendered.markdown, metadata

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

            # Check if chunk contains a table
            has_table = self._contains_table(chunk_text)

            chunks.append({
                "text": chunk_text,
                "chunk_id": idx,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
                "token_count": chunk.token_count,
                "pages": chunk_pages,
                "page_range": f"{min(chunk_pages)}-{max(chunk_pages)}" if chunk_pages else "unknown",
                "has_table": has_table
            })

        return chunks

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
