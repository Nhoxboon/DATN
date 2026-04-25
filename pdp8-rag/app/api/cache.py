"""Cache management endpoints."""

from fastapi import APIRouter, HTTPException
from app.services.rag.dependencies import get_rag_service
from app.db.dependencies import get_document_repository, get_supabase_client
from typing import List, Dict, Any

router = APIRouter(prefix="/cache", tags=["cache"])


@router.post("/warmup")
async def warmup_cache(doc_names: List[str] = None) -> Dict[str, Any]:
    """
    Pre-cache documents for fast queries.

    Args:
        doc_names: List of document names to cache (if None, cache all)

    Returns:
        Cache status for each document
    """
    rag_service = get_rag_service()
    doc_repo = get_document_repository(get_supabase_client())

    # Get all documents if none specified
    if not doc_names:
        doc_names = doc_repo.list_documents()

    results = {}

    for doc_name in doc_names:
        try:
            # Check if already cached
            cache_name = rag_service.cache_service.get_cache_name(doc_name)

            if cache_name:
                results[doc_name] = {"status": "already_cached", "cache_name": cache_name}
                continue

            # Retrieve representative chunks (use a general query)
            chunks = rag_service.retrieval_service.retrieve(
                query="overview summary main points key information",
                doc_names=[doc_name]
            )

            # Create cache
            cache_name = rag_service.cache_service.create_document_cache(
                doc_name=doc_name,
                chunks=chunks[:15],  # Limit to 15 chunks for reasonable cache size
                ttl_hours=24  # Cache for 24 hours
            )

            if cache_name:
                results[doc_name] = {"status": "cached", "cache_name": cache_name, "chunks": len(chunks[:15])}
            else:
                results[doc_name] = {"status": "failed", "reason": "Cache creation failed"}

        except Exception as e:
            results[doc_name] = {"status": "error", "error": str(e)}

    return {
        "total_documents": len(doc_names),
        "results": results
    }


@router.get("/status")
async def cache_status() -> Dict[str, Any]:
    """Get status of all document caches."""
    rag_service = get_rag_service()
    doc_repo = get_document_repository(get_supabase_client())

    all_docs = doc_repo.list_documents()

    status = {
        "total_documents": len(all_docs),
        "cached_documents": [],
        "uncached_documents": []
    }

    for doc_name in all_docs:
        cache_name = rag_service.cache_service.get_cache_name(doc_name)
        if cache_name:
            status["cached_documents"].append({
                "document": doc_name,
                "cache_name": cache_name
            })
        else:
            status["uncached_documents"].append(doc_name)

    status["cached_count"] = len(status["cached_documents"])
    status["uncached_count"] = len(status["uncached_documents"])

    return status


@router.delete("/clear")
async def clear_cache(doc_name: str = None) -> Dict[str, str]:
    """
    Clear document cache(s).

    Args:
        doc_name: Document name to clear (if None, clear all)

    Returns:
        Status message
    """
    rag_service = get_rag_service()

    if doc_name:
        success = rag_service.cache_service.delete_cache(doc_name)
        if success:
            return {"status": "success", "message": f"Cache cleared for {doc_name}"}
        else:
            raise HTTPException(status_code=404, detail=f"No cache found for {doc_name}")
    else:
        # Clear all caches
        doc_repo = get_document_repository(get_supabase_client())
        all_docs = doc_repo.list_documents()

        cleared = 0
        for doc in all_docs:
            if rag_service.cache_service.delete_cache(doc):
                cleared += 1

        return {"status": "success", "message": f"Cleared {cleared} cache(s)"}
