"""Notebook workspace routes."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.db.dependencies import get_supabase_admin_client
from app.schemas.auth import CurrentUser
from app.schemas.notebooks import (
    ChatCurrentResponse,
    ChatSendRequest,
    ChatSendResponse,
    DocumentStatus,
    DocumentUploadResponse,
    NoteCreateRequest,
    NotebookCreateRequest,
    NotebookDetail,
    NotebookNote,
    NotebookSummary,
    NotebookUpdateRequest,
)
from app.services.auth.dependencies import get_current_user
from app.services.notebooks import (
    NotebookNotFoundError,
    NotebookValidationError,
    NotebookWorkspaceService,
    get_notebook_workspace_service,
)


router = APIRouter(prefix="/notebooks", tags=["notebooks"])
logger = logging.getLogger(__name__)


def get_workspace_service(
    supabase_client: Any = Depends(get_supabase_admin_client),
) -> NotebookWorkspaceService:
    """Return notebook workspace service."""
    return get_notebook_workspace_service(supabase_client)


def _handle_notebook_error(exc: Exception) -> None:
    if isinstance(exc, NotebookNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, NotebookValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[NotebookSummary])
async def list_notebooks(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> list[NotebookSummary]:
    """List notebooks owned by the current user."""
    logger.info("GET /notebooks user_id=%s", current_user.id)
    return service.list_notebooks(current_user.id)


@router.post("", response_model=NotebookDetail, status_code=status.HTTP_201_CREATED)
async def create_notebook(
    payload: NotebookCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookDetail:
    """Create a notebook for the current user."""
    try:
        return service.create_notebook(current_user.id, payload.title, payload.description)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.get("/{notebook_id}", response_model=NotebookDetail)
async def get_notebook(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookDetail:
    """Get a notebook owned by the current user."""
    try:
        logger.info("GET /notebooks/%s user_id=%s", notebook_id, current_user.id)
        return service.get_notebook(current_user.id, notebook_id)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.patch("/{notebook_id}", response_model=NotebookDetail)
async def update_notebook(
    notebook_id: str,
    payload: NotebookUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookDetail:
    """Update a notebook owned by the current user."""
    try:
        return service.update_notebook(current_user.id, notebook_id, payload.title, payload.description)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.delete("/{notebook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notebook(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> None:
    """Delete a notebook owned by the current user."""
    try:
        service.delete_notebook(current_user.id, notebook_id)
    except Exception as exc:
        _handle_notebook_error(exc)


@router.get("/{notebook_id}/documents", response_model=list[DocumentStatus])
async def list_documents(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> list[DocumentStatus]:
    """List document processing states for a notebook."""
    try:
        return service.list_documents(current_user.id, notebook_id)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.post("/{notebook_id}/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    notebook_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> DocumentUploadResponse:
    """Upload and synchronously index a PDF into a notebook."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required.")

    try:
        content = await file.read()
        logger.info(
            "POST /notebooks/%s/documents/upload user_id=%s filename=%s bytes=%s",
            notebook_id,
            current_user.id,
            file.filename,
            len(content),
        )
        result = service.upload_document(current_user.id, notebook_id, content, file.filename)
        documents = service.list_documents(current_user.id, notebook_id)
        logger.info(
            "POST /notebooks/%s/documents/upload completed document=%s queued=%s chunks=%s",
            notebook_id,
            result["document_name"],
            bool(result.get("queued", False)),
            result["chunks_processed"],
        )
        return DocumentUploadResponse(
            status="success",
            document_name=str(result["document_name"]),
            chunks_processed=int(result["chunks_processed"]),
            storage_path=str(result["storage_path"]),
            public_url=result.get("public_url"),
            queued=bool(result.get("queued", False)),
            documents=documents,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        _handle_notebook_error(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.delete("/{notebook_id}/documents/{document_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    notebook_id: str,
    document_name: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> None:
    """Delete a notebook document."""
    try:
        service.delete_document(current_user.id, notebook_id, document_name)
    except Exception as exc:
        _handle_notebook_error(exc)


@router.get("/{notebook_id}/chat/current", response_model=ChatCurrentResponse)
async def get_current_chat(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> ChatCurrentResponse:
    """Load the current persisted notebook conversation."""
    try:
        session_id, messages = service.get_current_chat(current_user.id, notebook_id)
        return ChatCurrentResponse(session_id=session_id, messages=messages)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.post("/{notebook_id}/chat/messages", response_model=ChatSendResponse)
async def send_chat_message(
    notebook_id: str,
    payload: ChatSendRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> ChatSendResponse:
    """Save a user question, answer it with notebook-scoped RAG, and save the AI reply."""
    try:
        logger.info(
            "POST /notebooks/%s/chat/messages user_id=%s selected_documents=%s",
            notebook_id,
            current_user.id,
            payload.document_names,
        )
        result = service.send_chat_message(
            current_user.id,
            notebook_id,
            payload.message,
            payload.document_names,
        )
        return ChatSendResponse(**result)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc


@router.post("/{notebook_id}/chat/new", response_model=ChatCurrentResponse)
async def new_chat(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> ChatCurrentResponse:
    """Clear the current notebook chat and start a new one."""
    try:
        session_id, messages = service.new_chat(current_user.id, notebook_id)
        return ChatCurrentResponse(session_id=session_id, messages=messages)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.get("/{notebook_id}/notes", response_model=list[NotebookNote])
async def list_notes(
    notebook_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> list[NotebookNote]:
    """List saved Studio notes."""
    try:
        return service.list_notes(current_user.id, notebook_id)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.post("/{notebook_id}/notes", response_model=NotebookNote, status_code=status.HTTP_201_CREATED)
async def create_note(
    notebook_id: str,
    payload: NoteCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookNote:
    """Save one AI answer into Studio notes."""
    try:
        return service.create_note(
            current_user.id,
            notebook_id,
            payload.question,
            payload.answer,
            payload.sources,
            payload.document_names,
        )
    except Exception as exc:
        _handle_notebook_error(exc)
        raise
