"""Notebook, document, chat, and note schemas."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class NotebookCreateRequest(BaseModel):
    """Create notebook payload."""

    title: str = Field(default="Untitled Notebook", min_length=1, max_length=160)
    description: str | None = None


class NotebookUpdateRequest(BaseModel):
    """Update notebook payload."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None


class NotebookSummary(BaseModel):
    """Notebook shown on the dashboard."""

    id: str
    title: str
    description: str | None = None
    source_count: int = 0
    created_at: str
    updated_at: str


class DocumentStatus(BaseModel):
    """Document ingestion status inside a notebook."""

    id: str | None = None
    document_name: str
    status: Literal["pending", "processing", "completed", "failed"]
    total_chunks: int | None = None
    processed_chunks: int | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class NotebookNote(BaseModel):
    """Durable saved answer in Studio."""

    id: str
    question: str
    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    document_names: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class NotebookDetail(NotebookSummary):
    """Notebook detail with source and Studio note lists."""

    documents: list[DocumentStatus] = Field(default_factory=list)
    notes: list[NotebookNote] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    """Notebook document upload response."""

    status: str
    document_name: str
    chunks_processed: int
    storage_path: str
    public_url: str | None = None
    queued: bool = False
    documents: list[DocumentStatus] = Field(default_factory=list)


class ChatMessageOut(BaseModel):
    """Stored chat message."""

    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ChatCurrentResponse(BaseModel):
    """Current notebook chat session."""

    session_id: str
    messages: list[ChatMessageOut] = Field(default_factory=list)


class ChatSendRequest(BaseModel):
    """Send a notebook-scoped RAG question."""

    message: str = Field(..., min_length=1)
    document_names: list[str] = Field(default_factory=list)


class ChatSendResponse(ChatCurrentResponse):
    """Chat response after sending a message."""

    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    strategy: str | None = None
    strategy_reasoning: str | None = None


class NoteCreateRequest(BaseModel):
    """Persist one Q/A pair into Studio notes."""

    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    document_names: list[str] = Field(default_factory=list)
