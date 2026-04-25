"""Document processing Celery tasks."""

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
from app.workers.tasks.embedding import generate_embedding_and_store_task
from app.workers.tasks.storage import finalize_document_task
from pathlib import Path


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
@circuit_breaker("pdf_processing", failure_threshold=5, timeout=300)
def process_document_task(self, document_name: str, file_path: str):
    """
    Main orchestrator task for document processing with fan-out/fan-in.

    Args:
        document_name: Name of the document
        file_path: Path to the PDF file

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
        with distributed_lock(f"document:{document_name}", timeout=3600):
            # Create processing status
            status_repo.create_status(
                document_name=document_name,
                task_id=self.request.id
            )

            # Update status to processing
            status_repo.update_status(document_name, ProcessingStatus.PROCESSING)

            # Step 1: Upload to storage if not already uploaded
            if not file_path.startswith("http"):
                upload_result = storage_service.upload_pdf(file_path)
                storage_path = upload_result["path"]
            else:
                storage_path = file_path

            # Step 2: Extract and chunk document
            result = extract_and_chunk_task.apply_async(
                args=[document_name, file_path],
                queue="document_processing"
            )

            return {
                "task_id": self.request.id,
                "document_name": document_name,
                "status": "started",
                "extract_task_id": result.id
            }

    except CircuitBreakerOpen as e:
        status_repo.update_status(
            document_name,
            ProcessingStatus.FAILED,
            error_message=f"Circuit breaker open: {str(e)}"
        )
        raise self.retry(exc=e)

    except Exception as e:
        status_repo.update_status(
            document_name,
            ProcessingStatus.FAILED,
            error_message=str(e)
        )
        raise


@celery_app.task(bind=True, max_retries=3)
@circuit_breaker("pdf_extraction", failure_threshold=3, timeout=180)
def extract_and_chunk_task(self, document_name: str, file_path: str):
    """
    Extract PDF content and create chunks.

    Args:
        document_name: Name of the document
        file_path: Path to the PDF file

    Returns:
        Dict with chunks and metadata
    """
    settings = get_settings()
    app_config = get_app_config()

    try:
        # Initialize services with DI
        embedding_service = EmbeddingService(settings)
        pdf_processor = PDFProcessor(app_config, settings, embedding_service)

        # Process PDF
        markdown_content, metadata = pdf_processor.process_pdf(file_path)

        # Chunk with page preservation
        chunks = pdf_processor.chunk_text_with_pages(markdown_content, metadata)

        supabase_client = get_supabase_client()
        status_repo = get_processing_status_repository(supabase_client)

        # Update total chunks
        status_repo.update_status(
            document_name,
            ProcessingStatus.PROCESSING,
            processed_chunks=0
        )

        # Fan-out: Create embedding tasks for all chunks in parallel
        # Fan-in: Use chord to aggregate results and finalize
        embedding_tasks = group(
            generate_embedding_and_store_task.s(
                document_name=document_name,
                chunk_data=chunk
            )
            for chunk in chunks
        )

        # Chord: Run all embeddings in parallel, then finalize
        workflow = chord(embedding_tasks)(
            finalize_document_task.s(document_name=document_name, total_chunks=len(chunks))
        )

        return {
            "document_name": document_name,
            "total_chunks": len(chunks),
            "workflow_id": workflow.id
        }

    except Exception as e:
        supabase_client = get_supabase_client()
        status_repo = get_processing_status_repository(supabase_client)
        status_repo.update_status(
            document_name,
            ProcessingStatus.FAILED,
            error_message=f"Extraction failed: {str(e)}"
        )
        raise self.retry(exc=e)
