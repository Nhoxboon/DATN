"""RAG API endpoints."""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from app.services.rag.service import RAGService
from app.schemas.rag import QueryRequest, QueryResponse

router = APIRouter(prefix="/rag", tags=["RAG"])

# Initialize RAG service (singleton)
rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create RAG service instance."""
    global rag_service
    if rag_service is None:
        rag_service = RAGService(use_optimized=True)
    return rag_service


@router.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest) -> QueryResponse:
    """
    Answer a question using RAG.

    Args:
        request: Query request with question

    Returns:
        Answer with sources and reasoning
    """
    try:
        service = get_rag_service()
        result = service.query(
            question=request.question,
            document_name=request.document_name
        )
        return QueryResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check if RAG service is ready."""
    try:
        service = get_rag_service()
        return {
            "status": "healthy",
            "is_optimized": service.is_optimized,
            "model": service.app_config.llm.gemini.model
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
