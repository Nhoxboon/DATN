"""Embedding generation Celery tasks."""

from typing import Dict, Any
from app.workers.celery_app import celery_app
from app.workers.middleware.circuit_breaker import circuit_breaker, CircuitBreakerOpen
from app.workers.middleware.rate_limiter import get_rate_limiter
from app.core.config import get_settings
from app.services.embedding import EmbeddingService
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository


@celery_app.task(bind=True, max_retries=5, default_retry_delay=30)
@circuit_breaker("gemini_embedding", failure_threshold=10, timeout=120)
def generate_embedding_and_store_task(
    self,
    document_name: str,
    chunk_data: Dict[str, Any]
):
    """
    Generate embedding for a chunk and store in database.
    Protected by circuit breaker and rate limiter.

    Args:
        document_name: Name of the document
        chunk_data: Chunk data dictionary

    Returns:
        Result dictionary with success status
    """
    settings = get_settings()

    # Get rate limiter for Gemini embeddings
    rate_limiter = get_rate_limiter("gemini_embedding")

    try:
        # Acquire rate limit token (blocking with 60s timeout)
        acquired = rate_limiter.acquire(tokens=1, blocking=True, timeout=60)

        if not acquired:
            # Rate limit exceeded, retry later
            raise self.retry(countdown=5, exc=Exception("Rate limit exceeded"))

        # Generate embedding
        embedding_service = EmbeddingService(settings)
        embedding = embedding_service.embed_text(chunk_data["text"])

        # Store in database
        supabase_client = get_supabase_client()
        doc_repo = get_document_repository(supabase_client)

        doc_repo.insert_chunk(
            document_name=document_name,
            chunk_id=chunk_data["chunk_id"],
            content=chunk_data["text"],
            embedding=embedding,
            metadata={
                "start_index": chunk_data["start_index"],
                "end_index": chunk_data["end_index"],
                "token_count": chunk_data["token_count"],
                "has_table": chunk_data.get("has_table", False)
            },
            pages=chunk_data["pages"],
            page_range=chunk_data["page_range"]
        )

        return {
            "chunk_id": chunk_data["chunk_id"],
            "success": True,
            "document_name": document_name
        }

    except CircuitBreakerOpen as e:
        # Circuit is open, retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries * 10)

    except Exception as e:
        # Log error and retry
        print(f"Error processing chunk {chunk_data['chunk_id']}: {str(e)}")
        raise self.retry(exc=e)
