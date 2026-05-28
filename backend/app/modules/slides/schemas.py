"""Schemas for notebook slide decks."""

from typing import Any, Literal

from pydantic import BaseModel, Field


SlideDeckStatus = Literal["pending", "processing", "completed", "failed"]


class SlideDeckCreateRequest(BaseModel):
    """Create a slide deck from selected notebook documents."""

    document_names: list[str] = Field(default_factory=list)


class SlideDeckOut(BaseModel):
    """Slide deck shown in the Studio panel."""

    id: str
    notebook_id: str
    status: SlideDeckStatus
    storage_path: str | None = None
    title: str
    deck_json: dict[str, Any] | None = None
    document_names: list[str] = Field(default_factory=list)
    source_count: int = 0
    content_type: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class SlideDeckUrlResponse(BaseModel):
    """Signed URL for a generated PDF slide deck."""

    pdf_url: str
    expires_in: int
