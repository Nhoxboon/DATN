"""Routes for notebook slide decks."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.dependencies import get_supabase_admin_client
from app.modules.slides.schemas import SlideDeckCreateRequest, SlideDeckOut, SlideDeckUrlResponse
from app.modules.slides.service import (
    SlideDeckNotFoundError,
    SlideDeckService,
    SlideDeckValidationError,
    get_slide_deck_service,
)
from app.schemas.auth import CurrentUser
from app.services.auth.dependencies import get_current_user


router = APIRouter(prefix="/notebooks/{notebook_id}/slides", tags=["slides"])


def get_service(supabase_client: Any = Depends(get_supabase_admin_client)) -> SlideDeckService:
    """Return the slide deck service."""
    return get_slide_deck_service(supabase_client)


def handle_slide_error(exc: Exception) -> None:
    """Translate module exceptions to HTTP errors."""
    if isinstance(exc, SlideDeckNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, SlideDeckValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[SlideDeckOut])
async def list_slide_decks(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: SlideDeckService = Depends(get_service),
) -> list[SlideDeckOut]:
    """List slide decks for a notebook."""
    try:
        return service.list_slide_decks(current_user.id, notebook_id)
    except Exception as exc:
        handle_slide_error(exc)
        raise


@router.post("", response_model=SlideDeckOut, status_code=status.HTTP_201_CREATED)
async def create_slide_deck(
    notebook_id: str,
    payload: SlideDeckCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: SlideDeckService = Depends(get_service),
) -> SlideDeckOut:
    """Create a slide deck from selected notebook sources."""
    try:
        return service.create_slide_deck(current_user.id, notebook_id, payload.document_names)
    except Exception as exc:
        handle_slide_error(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.get("/{slide_id}/pdf-url", response_model=SlideDeckUrlResponse)
async def get_slide_deck_pdf_url(
    notebook_id: str,
    slide_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: SlideDeckService = Depends(get_service),
) -> SlideDeckUrlResponse:
    """Create a signed URL for a completed slide deck PDF."""
    try:
        expires_in = 3600
        return SlideDeckUrlResponse(
            pdf_url=service.get_pdf_url(current_user.id, notebook_id, slide_id, expires_in),
            expires_in=expires_in,
        )
    except Exception as exc:
        handle_slide_error(exc)
        raise


@router.delete("/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slide_deck(
    notebook_id: str,
    slide_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: SlideDeckService = Depends(get_service),
) -> None:
    """Delete a slide deck and its stored PDF object."""
    try:
        service.delete_slide_deck(current_user.id, notebook_id, slide_id)
    except Exception as exc:
        handle_slide_error(exc)
