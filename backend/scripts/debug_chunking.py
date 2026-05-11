"""Read-only PDF extraction and chunking parity debug command.

Run this from the target project environment so the command uses that
project's dependencies and config:

    cd backend
    uv run python scripts/debug_chunking.py /path/to/file.pdf

    cd ../pdp8-rag
    uv run python ../backend/scripts/debug_chunking.py /path/to/file.pdf --project-root .
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def _snippet(value: str, length: int = 200) -> str:
    return value[:length].replace("\n", "\\n")


def _tail(value: str, length: int = 200) -> str:
    return value[-length:].replace("\n", "\\n")


def _download_pdf(url: str) -> Path:
    suffix = Path(urllib.parse.urlparse(url).path).suffix or ".pdf"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp_file.write(data)
    temp_file.close()
    return Path(temp_file.name)


def _resolve_pdf(source: str) -> tuple[Path, bool]:
    if source.startswith(("http://", "https://")):
        return _download_pdf(source), True
    return Path(source).expanduser().resolve(), False


def _load_processor(project_root: Path) -> Any:
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))

    from app.core.config import get_app_config, get_settings
    from app.services.embedding import EmbeddingService
    from app.services.pdf_processor.processor import PDFProcessor

    settings = get_settings()
    app_config = get_app_config()
    embedding_service = EmbeddingService(settings)
    return PDFProcessor(app_config, settings, embedding_service)


def run_debug(pdf_source: str, project_root: Path) -> int:
    pdf_path, should_cleanup = _resolve_pdf(pdf_source)
    try:
        if not pdf_path.exists():
            print(f"PDF not found: {pdf_path}", file=sys.stderr)
            return 2

        processor = _load_processor(project_root.resolve())
        markdown, metadata = processor.process_pdf(str(pdf_path))
        chunks = processor.chunk_text_with_pages(markdown, metadata)

        print(f"Project root: {project_root.resolve()}")
        print(f"PDF source: {pdf_source}")
        print(f"Resolved PDF: {pdf_path}")
        print(f"Markdown chars: {len(markdown)}")
        print(f"Markdown first 200: {_snippet(markdown)}")
        print(f"Markdown last 200: {_tail(markdown)}")
        print(f"Total pages: {metadata.get('total_pages')}")
        print(f"Image count: {metadata.get('image_count', 0)}")
        print(f"Describe images: {metadata.get('describe_images')}")
        print(f"Chunk count: {len(chunks)}")

        for chunk in chunks:
            text = chunk.get("text", "")
            print(
                "Chunk "
                f"{chunk.get('chunk_id')}: "
                f"chars={len(text)} "
                f"tokens={chunk.get('token_count')} "
                f"pages={chunk.get('pages')} "
                f"page_range={chunk.get('page_range')} "
                f"content_type={chunk.get('content_type')}"
            )
            print(f"  first 200: {_snippet(text)}")
            print(f"  last 200: {_tail(text)}")

        return 0
    finally:
        if should_cleanup:
            try:
                pdf_path.unlink()
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug PDF extraction/chunking without writing to DB.")
    parser.add_argument("pdf", help="Local PDF path or public HTTP(S) URL")
    parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        type=Path,
        help="Project root whose app/config/dependencies should be used",
    )
    args = parser.parse_args()
    return run_debug(args.pdf, args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
