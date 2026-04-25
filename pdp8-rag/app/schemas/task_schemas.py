"""Pydantic schemas for Celery tasks."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChunkData(BaseModel):
    """Schema for a document chunk."""
    text: str
    chunk_id: int
    start_index: int
    end_index: int
    token_count: int
    pages: List[int]
    page_range: str
    has_table: bool = False


class DocumentMetadata(BaseModel):
    """Schema for document metadata."""
    total_pages: Optional[int] = None
    images: List[str] = Field(default_factory=list)


class ProcessDocumentRequest(BaseModel):
    """Request schema for document processing."""
    document_name: str
    file_path: str


class EmbeddingTaskResult(BaseModel):
    """Result schema for embedding task."""
    chunk_id: int
    embedding: List[float]
    success: bool
    error: Optional[str] = None


class DocumentProcessingResult(BaseModel):
    """Final result of document processing."""
    document_name: str
    total_chunks: int
    processed_chunks: int
    failed_chunks: int
    success: bool
    error: Optional[str] = None
