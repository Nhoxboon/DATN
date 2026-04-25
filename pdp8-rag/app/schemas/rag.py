"""Schemas for RAG endpoints."""

from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    """Request model for RAG query."""
    question: str = Field(..., description="Question about PDP8 regulation", min_length=1)
    document_name: str = Field(
        default="PDP8_full-with-annexes_EN",
        description="Document to search"
    )


class SourceInfo(BaseModel):
    """Source information for retrieved chunks."""
    content: str
    document: str
    pages: List[int]
    page_range: str
    similarity: float


class QueryResponse(BaseModel):
    """Response model for RAG query."""
    question: str
    answer: str
    reasoning: Optional[str] = None
    sources: List[SourceInfo]
    is_optimized: bool
