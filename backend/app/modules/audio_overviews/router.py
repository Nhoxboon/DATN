"""Routes for notebook audio overviews."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.dependencies import get_supabase_admin_client
from app.modules.audio_overviews.schemas import (
    AudioOverviewCreateRequest,
    AudioOverviewOut,
    AudioOverviewUrlResponse,
)
from app.modules.audio_overviews.service import (
    AudioOverviewNotFoundError,
    AudioOverviewService,
    AudioOverviewValidationError,
    get_audio_overview_service,
)
from app.schemas.auth import CurrentUser
from app.services.auth.dependencies import get_current_user


router = APIRouter(prefix="/notebooks/{notebook_id}/audio-overviews", tags=["audio-overviews"])


def get_service(supabase_client: Any = Depends(get_supabase_admin_client)) -> AudioOverviewService:
    """Return the audio overview service."""
    return get_audio_overview_service(supabase_client)


def handle_audio_error(exc: Exception) -> None:
    """Translate module exceptions to HTTP errors."""
    if isinstance(exc, AudioOverviewNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, AudioOverviewValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[AudioOverviewOut])
async def list_audio_overviews(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioOverviewService = Depends(get_service),
) -> list[AudioOverviewOut]:
    """List audio overviews for a notebook."""
    try:
        return service.list_audio_overviews(current_user.id, notebook_id)
    except Exception as exc:
        handle_audio_error(exc)
        raise


@router.post("", response_model=AudioOverviewOut, status_code=status.HTTP_201_CREATED)
async def create_audio_overview(
    notebook_id: str,
    payload: AudioOverviewCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioOverviewService = Depends(get_service),
) -> AudioOverviewOut:
    """Create an audio overview from selected notebook sources."""
    try:
        return service.create_audio_overview(current_user.id, notebook_id, payload.document_names)
    except Exception as exc:
        handle_audio_error(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/{overview_id}/audio-url", response_model=AudioOverviewUrlResponse)
async def get_audio_overview_url(
    notebook_id: str,
    overview_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioOverviewService = Depends(get_service),
) -> AudioOverviewUrlResponse:
    """Create a signed URL for completed audio playback."""
    try:
        expires_in = 3600
        return AudioOverviewUrlResponse(
            audio_url=service.get_audio_url(current_user.id, notebook_id, overview_id, expires_in),
            expires_in=expires_in,
        )
    except Exception as exc:
        handle_audio_error(exc)
        raise


@router.delete("/{overview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audio_overview(
    notebook_id: str,
    overview_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: AudioOverviewService = Depends(get_service),
) -> None:
    """Delete an audio overview and its stored audio object."""
    try:
        service.delete_audio_overview(current_user.id, notebook_id, overview_id)
    except Exception as exc:
        handle_audio_error(exc)
