"""Schemas for notebook audio overviews."""

from typing import Literal

from pydantic import BaseModel, Field


AudioOverviewStatus = Literal["pending", "processing", "completed", "failed"]


class AudioOverviewCreateRequest(BaseModel):
    """Create an audio overview from selected notebook documents."""

    document_names: list[str] = Field(default_factory=list)


class AudioOverviewOut(BaseModel):
    """Audio overview shown in the Studio panel."""

    id: str
    notebook_id: str
    status: AudioOverviewStatus
    storage_path: str | None = None
    title: str
    style: str | None = None
    script_text: str | None = None
    document_names: list[str] = Field(default_factory=list)
    duration_seconds: float | None = None
    content_type: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str


class AudioOverviewUrlResponse(BaseModel):
    """Signed URL for playback from a private storage bucket."""

    audio_url: str
    expires_in: int
