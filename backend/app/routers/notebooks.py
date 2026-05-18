"""Notebook workspace routes."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.db.dependencies import get_supabase_admin_client
from app.schemas.auth import CurrentUser
from app.schemas.notebooks import (
    ChatCurrentResponse,
    ChatSendRequest,
    ChatSendResponse,
    DocumentRenameRequest,
    DocumentStatus,
    DocumentUploadResponse,
    NoteCreateRequest,
    NoteUpdateRequest,
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
from app.services.rag.dependencies import get_rag_service


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
    """Upload and queue a PDF or DOCX for worker indexing into a notebook."""
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


@router.post("/{notebook_id}/documents/rename", response_model=NotebookDetail)
async def rename_document_by_name(
    notebook_id: str,
    payload: DocumentRenameRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookDetail:
    """Rename a notebook source document by request body."""
    if not payload.current_document_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current source name is required.")

    try:
        return service.rename_document(
            current_user.id,
            notebook_id,
            payload.current_document_name,
            payload.document_name,
        )
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.patch("/{notebook_id}/documents/{document_name}", response_model=NotebookDetail)
async def rename_document(
    notebook_id: str,
    document_name: str,
    payload: DocumentRenameRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookDetail:
    """Rename a notebook source document."""
    try:
        return service.rename_document(current_user.id, notebook_id, document_name, payload.document_name)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


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


@router.patch("/{notebook_id}/notes/{note_id}", response_model=NotebookNote)
async def update_note(
    notebook_id: str,
    note_id: str,
    payload: NoteUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> NotebookNote:
    """Rename a saved Studio note."""
    try:
        return service.update_note(current_user.id, notebook_id, note_id, payload.question)
    except Exception as exc:
        _handle_notebook_error(exc)
        raise


@router.delete("/{notebook_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    notebook_id: str,
    note_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> None:
    """Delete a saved Studio note."""
    try:
        service.delete_note(current_user.id, notebook_id, note_id)
    except Exception as exc:
        _handle_notebook_error(exc)


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


@router.post("/{notebook_id}/chat/messages/stream")
async def send_chat_message_stream(
    notebook_id: str,
    payload: ChatSendRequest,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotebookWorkspaceService = Depends(get_workspace_service),
) -> StreamingResponse:
    """Save a user question, stream notebook-scoped RAG tokens, and save the AI reply."""
    try:
        logger.info(
            "POST /notebooks/%s/chat/messages/stream user_id=%s selected_documents=%s",
            notebook_id,
            current_user.id,
            payload.document_names,
        )
        prepared = service.begin_chat_message(
            current_user.id,
            notebook_id,
            payload.message,
            payload.document_names,
        )
    except Exception as exc:
        _handle_notebook_error(exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    def ndjson_event(event: dict[str, Any]) -> str:
        return json.dumps(event, default=str) + "\n"

    async def event_generator():
        full_answer = ""
        metadata: dict[str, Any] = {}

        try:
            rag_service = get_rag_service()
            async for chunk in rag_service.query_stream(
                question=str(prepared["message"]),
                notebook_id=notebook_id,
                doc_names=prepared["document_names"],
            ):
                if chunk.get("type") == "token":
                    content = str(chunk.get("content", ""))
                    full_answer += content
                    yield ndjson_event({"type": "token", "content": content})
                elif chunk.get("type") == "metadata":
                    metadata = chunk
                    yield ndjson_event(
                        {
                            "type": "metadata",
                            "strategy": chunk.get("strategy"),
                            "strategy_reasoning": chunk.get("strategy_reasoning"),
                            "sources": chunk.get("sources", []),
                        }
                    )

            result = service.finalize_chat_message(
                current_user.id,
                notebook_id,
                str(prepared["session_id"]),
                full_answer,
                metadata.get("sources", []),
                metadata.get("strategy"),
                metadata.get("strategy_reasoning"),
            )
            yield ndjson_event(
                {
                    "type": "done",
                    "session_id": result["session_id"],
                    "messages": [message.model_dump() for message in result["messages"]],
                    "strategy": result.get("strategy"),
                    "strategy_reasoning": result.get("strategy_reasoning"),
                }
            )
        except Exception as exc:
            logger.exception("Notebook streaming chat failed notebook_id=%s user_id=%s", notebook_id, current_user.id)
            yield ndjson_event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
