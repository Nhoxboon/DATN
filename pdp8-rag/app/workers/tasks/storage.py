"""Storage and finalization Celery tasks."""

from typing import List, Dict, Any
from app.workers.celery_app import celery_app
from app.db.dependencies import get_supabase_client
from app.db.processing_status import get_processing_status_repository, ProcessingStatus


@celery_app.task(bind=True)
def finalize_document_task(self, results: List[Dict[str, Any]], document_name: str, total_chunks: int):
    """
    Finalize document processing after all embeddings are complete.
    This is the chord callback (fan-in).

    Args:
        results: List of results from embedding tasks
        document_name: Name of the document
        total_chunks: Total number of chunks

    Returns:
        Final processing result
    """
    supabase_client = get_supabase_client()
    status_repo = get_processing_status_repository(supabase_client)

    try:
        # Count successes and failures
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        if failed == 0:
            # All chunks processed successfully
            status_repo.update_status(
                document_name,
                ProcessingStatus.COMPLETED,
                processed_chunks=successful
            )

            return {
                "document_name": document_name,
                "status": "completed",
                "total_chunks": total_chunks,
                "processed_chunks": successful,
                "failed_chunks": failed
            }
        else:
            # Some chunks failed
            status_repo.update_status(
                document_name,
                ProcessingStatus.FAILED,
                processed_chunks=successful,
                error_message=f"{failed} chunks failed to process"
            )

            return {
                "document_name": document_name,
                "status": "partially_failed",
                "total_chunks": total_chunks,
                "processed_chunks": successful,
                "failed_chunks": failed
            }

    except Exception as e:
        status_repo.update_status(
            document_name,
            ProcessingStatus.FAILED,
            error_message=f"Finalization failed: {str(e)}"
        )

        raise
