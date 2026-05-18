"""Document processing Celery tasks."""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast
from celery import chord, group
from app.workers.celery_app import celery_app
from app.workers.middleware.circuit_breaker import circuit_breaker, CircuitBreakerOpen
from app.workers.middleware.distributed_lock import distributed_lock
from app.core.config import get_settings, get_app_config
from app.services.pdf_processor import PDFProcessor
from app.services.embedding import EmbeddingService
from app.services.storage import StorageService
from app.db.dependencies import get_supabase_client
from app.db.processing_status import get_processing_status_repository, ProcessingStatus
from app.db.repository import get_document_repository
from app.services.rag.cache_registry import invalidate_document_caches
from app.workers.tasks.embedding import generate_embedding_and_store_task
from app.workers.tasks.storage import finalize_document_task
from app.core.document_naming import safe_pdf_storage_path


logger = logging.getLogger(__name__)


def _ensure_pdf_for_processing(file_path: str, document_name: str) -> str:
    """Return a PDF path, converting DOCX uploads before the existing PDF pipeline."""
    if file_path.startswith("http"):
        return file_path

    source_path = Path(file_path)
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        return file_path
    if suffix == ".docx":
        return str(_convert_docx_to_pdf(source_path, document_name))

    raise ValueError("Only PDF and DOCX files are supported")


def _convert_docx_to_pdf(source_path: Path, document_name: str) -> Path:
    """Convert a DOCX upload to a stable PDF path for downstream PDF processing."""
    if not source_path.exists():
        raise FileNotFoundError(f"DOCX file not found: {source_path}")

    temp_output_path = Path(tempfile.mkdtemp(prefix="docx-to-pdf-", dir=_conversion_root()))
    target_path = temp_output_path / safe_pdf_storage_path(document_name)

    if target_path.exists():
        target_path.unlink()

    profile_dir = temp_output_path / "lo-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "soffice",
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--nodefault",
                "--nolockcheck",
                f"-env:UserInstallation={profile_dir.as_uri()}",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(temp_output_path),
                str(source_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except FileNotFoundError as exc:
        _cleanup_conversion_workspace(target_path)
        raise RuntimeError("LibreOffice command 'soffice' was not found in the worker runtime.") from exc
    except subprocess.TimeoutExpired as exc:
        _cleanup_conversion_workspace(target_path)
        raise RuntimeError(f"DOCX conversion timed out for {source_path.name}.") from exc

    if result.returncode != 0:
        _cleanup_conversion_workspace(target_path)
        details = _conversion_details(result)
        raise RuntimeError(f"DOCX conversion failed for {source_path.name}: {details}")

    libreoffice_output = _find_converted_pdf(temp_output_path, source_path)
    if libreoffice_output is None:
        _cleanup_conversion_workspace(target_path)
        details = _conversion_details(result)
        raise RuntimeError(f"DOCX conversion did not create a PDF for {source_path.name}. {details}")

    shutil.move(str(libreoffice_output), str(target_path))

    return target_path


def _conversion_root() -> Path:
    """Return a worker-owned temp root for converted PDFs."""
    root = Path(tempfile.gettempdir()) / "datn-docx-conversions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _find_converted_pdf(output_dir: Path, source_path: Path) -> Path | None:
    """Return the PDF LibreOffice produced, allowing for non-obvious output names."""
    preferred_output = output_dir / f"{source_path.stem}.pdf"
    if preferred_output.exists():
        return preferred_output

    pdf_outputs = sorted(
        (path for path in output_dir.rglob("*.pdf") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return pdf_outputs[0] if pdf_outputs else None


def _conversion_details(result: subprocess.CompletedProcess[str]) -> str:
    """Format LibreOffice output for status/error messages."""
    details = "\n".join(
        part.strip()
        for part in (result.stderr, result.stdout)
        if isinstance(part, str) and part.strip()
    )
    return details or "LibreOffice returned no output."


def _cleanup_conversion_workspace(file_path: str | Path) -> None:
    """Remove the per-conversion workspace after PDF extraction no longer needs it."""
    path = Path(file_path)
    root = _conversion_root().resolve()
    try:
        resolved_path = path.resolve()
        if root == resolved_path or root in resolved_path.parents:
            workspace = resolved_path.parent
            if workspace != root:
                shutil.rmtree(workspace, ignore_errors=True)
    except Exception:
        logger.info("Could not clean up DOCX conversion workspace path=%s", path, exc_info=True)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
@circuit_breaker("pdf_processing", failure_threshold=5, timeout=300)
def process_document_task(self, notebook_id: str, user_id: str, document_name: str, file_path: str):
    """
    Main orchestrator task for document processing with fan-out/fan-in.

    Args:
        notebook_id: Notebook that owns the document
        user_id: User that owns the notebook
        document_name: Name of the document
        file_path: Path to the uploaded PDF or DOCX file

    Returns:
        Task ID for tracking
    """
    settings = get_settings()
    app_config = get_app_config()

    supabase_client = get_supabase_client()
    status_repo = get_processing_status_repository(supabase_client)
    storage_service = StorageService(supabase_client)

    try:
        # Acquire distributed lock to prevent duplicate processing
        with distributed_lock(f"document:{notebook_id}:{document_name}", timeout=3600):
            logger.info(
                "Worker document processing started notebook_id=%s user_id=%s document=%s task_id=%s file_path=%s",
                notebook_id,
                user_id,
                document_name,
                self.request.id,
                file_path,
            )
            # Create processing status
            status_repo.create_status(
                notebook_id=notebook_id,
                user_id=user_id,
                document_name=document_name,
                task_id=self.request.id
            )

            # Update status to processing
            status_repo.update_status(notebook_id, document_name, ProcessingStatus.PROCESSING)

            file_path = _ensure_pdf_for_processing(file_path, document_name)

            # Step 1: Upload to storage if not already uploaded
            if not file_path.startswith("http"):
                storage_service.upload_pdf(
                    file_path,
                    destination_path=f"{user_id}/{notebook_id}/{safe_pdf_storage_path(document_name)}"
                )

            # Step 2: Extract and chunk document
            result = cast(Any, extract_and_chunk_task).apply_async(
                args=[notebook_id, user_id, document_name, file_path],
                queue="document_processing"
            )

            return {
                "task_id": self.request.id,
                "document_name": document_name,
                "status": "started",
                "extract_task_id": result.id
            }

    except CircuitBreakerOpen as e:
        logger.exception(
            "Worker document processing circuit open notebook_id=%s document=%s",
            notebook_id,
            document_name,
        )
        status_repo.update_status(
            notebook_id,
            document_name,
            ProcessingStatus.FAILED,
            error_message=f"Circuit breaker open: {str(e)}"
        )
        raise self.retry(exc=e)

    except Exception as e:
        logger.exception(
            "Worker document processing failed notebook_id=%s document=%s",
            notebook_id,
            document_name,
        )
        status_repo.update_status(
            notebook_id,
            document_name,
            ProcessingStatus.FAILED,
            error_message=str(e)
        )
        raise


@celery_app.task(bind=True, max_retries=3)
@circuit_breaker("pdf_extraction", failure_threshold=3, timeout=180)
def extract_and_chunk_task(self, notebook_id: str, user_id: str, document_name: str, file_path: str):
    """
    Extract PDF content and create chunks.

    Args:
        notebook_id: Notebook that owns the document
        user_id: User that owns the notebook
        document_name: Name of the document
        file_path: Path to the PDF file

    Returns:
        Dict with chunks and metadata
    """
    settings = get_settings()
    app_config = get_app_config()

    try:
        logger.info(
            "Worker extract/chunk started notebook_id=%s user_id=%s document=%s file_path=%s",
            notebook_id,
            user_id,
            document_name,
            file_path,
        )
        # Initialize services with DI
        embedding_service = EmbeddingService(settings)
        pdf_processor = PDFProcessor(app_config, settings, embedding_service)

        # Process PDF
        markdown_content, metadata = pdf_processor.process_pdf(file_path)
        logger.info(
            "Worker PDF extracted notebook_id=%s document=%s markdown_chars=%s pages=%s images=%s",
            notebook_id,
            document_name,
            len(markdown_content),
            metadata.get("total_pages"),
            metadata.get("image_count", 0),
        )

        # Chunk with page preservation
        chunks = pdf_processor.chunk_text_with_pages(markdown_content, metadata)
        logger.info(
            "Worker chunking completed notebook_id=%s document=%s chunks=%s",
            notebook_id,
            document_name,
            len(chunks),
        )

        supabase_client = get_supabase_client()
        status_repo = get_processing_status_repository(supabase_client)
        doc_repo = get_document_repository(supabase_client)

        # Replace existing chunks for this document so re-indexing writes a
        # clean image-aware corpus instead of duplicating stale text-only rows.
        invalidate_document_caches(notebook_id, document_name)
        doc_repo.delete_by_name(document_name, notebook_id)

        # Update total chunks
        status_repo.update_status(
            notebook_id,
            document_name,
            ProcessingStatus.PROCESSING,
            processed_chunks=0,
            total_chunks=len(chunks)
        )

        # Fan-out: Create embedding tasks for all chunks in parallel
        # Fan-in: Use chord to aggregate results and finalize
        embedding_tasks = group(
            cast(Any, generate_embedding_and_store_task).s(
                document_name=document_name,
                notebook_id=notebook_id,
                user_id=user_id,
                chunk_data=chunk
            )
            for chunk in chunks
        )

        # Chord: Run all embeddings in parallel, then finalize
        workflow = chord(embedding_tasks)(
            cast(Any, finalize_document_task).s(
                document_name=document_name,
                notebook_id=notebook_id,
                total_chunks=len(chunks)
            )
        )

        result = {
            "document_name": document_name,
            "total_chunks": len(chunks),
            "workflow_id": workflow.id
        }
        _cleanup_conversion_workspace(file_path)
        return result

    except Exception as e:
        logger.exception(
            "Worker extract/chunk failed notebook_id=%s document=%s",
            notebook_id,
            document_name,
        )
        supabase_client = get_supabase_client()
        status_repo = get_processing_status_repository(supabase_client)
        status_repo.update_status(
            notebook_id,
            document_name,
            ProcessingStatus.FAILED,
            error_message=f"Extraction failed: {str(e)}"
        )
        raise self.retry(exc=e)
