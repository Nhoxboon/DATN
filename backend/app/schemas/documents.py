"""Document management schemas."""

from pydantic import BaseModel, Field
from typing import List, Optional


class DocumentListResponse(BaseModel):
    """Response model for listing documents."""

    documents: List[str] = Field(..., description="List of document names")
    count: int = Field(..., description="Total number of documents")


class DocumentUploadResponse(BaseModel):
    """Response model for document upload."""

    status: str = Field(..., description="Upload status")
    document_name: str = Field(..., description="Name of the uploaded document")
    chunks_processed: int = Field(..., description="Number of chunks created")
    storage_path: str = Field(..., description="Path in Supabase Storage")
    public_url: Optional[str] = Field(None, description="Public URL to access the file")


class DocumentDeleteResponse(BaseModel):
    """Response model for document deletion."""

    status: str = Field(..., description="Deletion status")
    document_name: str = Field(..., description="Name of the deleted document")
    message: str = Field(..., description="Success message")


class DocumentUploadRequest(BaseModel):
    """Request model for document upload from path."""

    file_path: str = Field(..., description="Absolute path to the PDF file")
    document_name: Optional[str] = Field(None, description="Optional custom document name")
