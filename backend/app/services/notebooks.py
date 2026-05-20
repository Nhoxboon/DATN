"""Notebook workspace service."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from celery import Celery

from app.core.config import get_settings
from app.core.document_naming import (
    document_extension_from_filename,
    document_name_from_filename,
    normalize_document_name,
    safe_document_storage_path,
    safe_pdf_storage_path,
)
from app.db.processing_status import ProcessingStatus, get_processing_status_repository
from app.db.repository import get_document_repository
from app.services.rag.cache_registry import invalidate_document_caches
from app.schemas.notebooks import (
    ChatMessageOut,
    DocumentStatus,
    NotebookDetail,
    NotebookNote,
    NotebookSummary,
)


logger = logging.getLogger(__name__)
CITATION_PATTERN = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
STORAGE_REMOVE_BATCH_SIZE = 1000


class NotebookNotFoundError(ValueError):
    """Raised when a notebook is not owned by the current user."""


class NotebookValidationError(ValueError):
    """Raised when notebook input is invalid."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first(data: Any) -> dict[str, Any] | None:
    return data[0] if isinstance(data, list) and data else None


class NotebookWorkspaceService:
    """High-level service for authenticated notebook workflows."""

    def __init__(self, supabase_client: Any):
        self.client = supabase_client

    def list_notebooks(self, user_id: str) -> list[NotebookSummary]:
        result = (
            self.client.table("notebooks")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        notebooks = result.data if isinstance(result.data, list) else []
        counts = self._source_counts(user_id)
        return [self._summary(row, counts.get(str(row["id"]), 0)) for row in notebooks]

    def create_notebook(
        self,
        user_id: str,
        title: str = "Untitled Notebook",
        description: str | None = None,
    ) -> NotebookDetail:
        clean_title = title.strip() or "Untitled Notebook"
        result = (
            self.client.table("notebooks")
            .insert({"user_id": user_id, "title": clean_title, "description": description})
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookValidationError("Notebook could not be created.")
        return self.get_notebook(user_id, str(row["id"]))

    def get_notebook(self, user_id: str, notebook_id: str) -> NotebookDetail:
        notebook = self._require_notebook(user_id, notebook_id)
        documents = self.list_documents(user_id, notebook_id)
        notes = self.list_notes(user_id, notebook_id)
        summary = self._summary(notebook, len([doc for doc in documents if doc.status == "completed"]))
        return NotebookDetail(**summary.model_dump(), documents=documents, notes=notes)

    def update_notebook(
        self,
        user_id: str,
        notebook_id: str,
        title: str | None = None,
        description: str | None = None,
    ) -> NotebookDetail:
        self._require_notebook(user_id, notebook_id)
        updates: dict[str, Any] = {"updated_at": _utc_now()}
        if title is not None:
            updates["title"] = title.strip() or "Untitled Notebook"
        if description is not None:
            updates["description"] = description
        (
            self.client.table("notebooks")
            .update(updates)
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        return self.get_notebook(user_id, notebook_id)

    def delete_notebook(self, user_id: str, notebook_id: str) -> None:
        self._require_notebook(user_id, notebook_id)
        source_storage_paths = self._storage_paths_for_notebook(user_id, notebook_id)
        audio_storage_paths = self._audio_storage_paths_for_notebook(user_id, notebook_id)
        self._revoke_notebook_tasks(user_id, notebook_id)
        (
            self.client.table("notebooks")
            .delete()
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        self._delete_storage_paths(source_storage_paths)
        self._delete_audio_storage_paths(audio_storage_paths)

    def list_documents(self, user_id: str, notebook_id: str) -> list[DocumentStatus]:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("document_processing_status")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        return [self._document_status(row) for row in rows]

    def upload_document(
        self,
        user_id: str,
        notebook_id: str,
        file_content: bytes,
        filename: str,
    ) -> dict[str, Any]:
        notebook = self._require_notebook(user_id, notebook_id)
        document_name = document_name_from_filename(filename)
        source_extension = document_extension_from_filename(filename)
        status_repo = get_processing_status_repository(self.client)
        status_created = False

        try:
            settings = get_settings()
            self._auto_title_from_first_upload(user_id, notebook_id, notebook, document_name)
            if settings.document_processing_mode.strip().lower() != "worker":
                raise NotebookValidationError(
                    "Document upload requires worker mode. Set DOCUMENT_PROCESSING_MODE=worker "
                    "and run the Celery worker."
                )
            self._invalidate_document_cache(notebook_id, document_name)

            task_id = str(uuid4())
            upload_dir = Path(settings.uploads_dir) / user_id / notebook_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / safe_document_storage_path(document_name, source_extension)
            file_path.write_bytes(file_content)
            logger.info(
                "Queued notebook document upload notebook_id=%s user_id=%s document=%s task_id=%s path=%s bytes=%s",
                notebook_id,
                user_id,
                document_name,
                task_id,
                file_path,
                len(file_content),
            )

            status_repo.create_status(
                notebook_id=notebook_id,
                user_id=user_id,
                document_name=document_name,
                task_id=task_id,
            )
            status_created = True
            self._celery_app(settings.redis_url).send_task(
                "app.workers.tasks.document.process_document_task",
                args=[notebook_id, user_id, document_name, str(file_path)],
                queue="document_processing",
                task_id=task_id,
            )
            self._touch_notebook(user_id, notebook_id)
            return {
                "document_name": document_name,
                "chunks_processed": 0,
                "storage_path": str(file_path),
                "public_url": None,
                "queued": True,
            }
        except Exception as exc:
            logger.exception(
                "Notebook document upload failed notebook_id=%s user_id=%s document=%s",
                notebook_id,
                user_id,
                document_name,
            )
            if status_created:
                status_repo.update_status(
                    notebook_id,
                    document_name,
                    ProcessingStatus.FAILED,
                    error_message=str(exc),
                )
            raise

    def delete_document(self, user_id: str, notebook_id: str, document_name: str) -> None:
        clean_document_name = self._clean_document_title(document_name)
        source = self._document_status_row(user_id, notebook_id, clean_document_name)
        if not source:
            self._require_notebook(user_id, notebook_id)
            return

        storage_paths = self._storage_paths_for_document(user_id, notebook_id, clean_document_name)

        self._revoke_processing_task(source)
        get_document_repository(self.client).delete_by_name(clean_document_name, notebook_id)
        get_processing_status_repository(self.client).delete_status(notebook_id, clean_document_name)
        self._invalidate_document_cache(notebook_id, clean_document_name)
        self._delete_storage_paths(storage_paths)
        self._delete_local_upload(user_id, notebook_id, clean_document_name)
        self._touch_notebook(user_id, notebook_id)

    def rename_document(
        self,
        user_id: str,
        notebook_id: str,
        document_name: str,
        next_document_name: str,
    ) -> NotebookDetail:
        current_name = self._clean_document_title(document_name)
        next_name = self._clean_document_title(next_document_name)

        if current_name == next_name:
            return self.get_notebook(user_id, notebook_id)

        source = self._require_document_status(user_id, notebook_id, current_name)
        if source.get("status") in {ProcessingStatus.PENDING, ProcessingStatus.PROCESSING}:
            raise NotebookValidationError("Wait until indexing finishes before renaming this source.")

        existing = (
            self.client.table("document_processing_status")
            .select("id")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .eq("document_name", next_name)
            .limit(1)
            .execute()
        )
        if _first(existing.data):
            raise NotebookValidationError(f'A source named "{next_name}" already exists in this notebook.')

        (
            self.client.table("document_processing_status")
            .update({"document_name": next_name, "updated_at": _utc_now()})
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .eq("document_name", current_name)
            .execute()
        )
        (
            self.client.table("documents")
            .update({"document_name": next_name})
            .eq("notebook_id", notebook_id)
            .eq("document_name", current_name)
            .execute()
        )
        self._invalidate_document_cache(notebook_id, current_name)
        self._invalidate_document_cache(notebook_id, next_name)
        self._rename_document_references(user_id, notebook_id, current_name, next_name)
        self._rename_local_upload(user_id, notebook_id, current_name, next_name)
        self._touch_notebook(user_id, notebook_id)
        return self.get_notebook(user_id, notebook_id)

    def get_current_chat(self, user_id: str, notebook_id: str) -> tuple[str, list[ChatMessageOut]]:
        session = self._get_or_create_session(user_id, notebook_id)
        return str(session["id"]), self._messages(str(session["id"]))

    def new_chat(self, user_id: str, notebook_id: str) -> tuple[str, list[ChatMessageOut]]:
        self._require_notebook(user_id, notebook_id)
        (
            self.client.table("chat_sessions")
            .delete()
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        session = self._create_session(user_id, notebook_id)
        self._touch_notebook(user_id, notebook_id)
        return str(session["id"]), []

    def send_chat_message(
        self,
        user_id: str,
        notebook_id: str,
        message: str,
        document_names: list[str],
    ) -> dict[str, Any]:
        self._require_notebook(user_id, notebook_id)
        selected_documents = self._validate_completed_documents(user_id, notebook_id, document_names)

        from app.services.rag.dependencies import get_rag_service

        result = get_rag_service().query(
            question=message.strip(),
            notebook_id=notebook_id,
            doc_names=selected_documents,
        )
        sources = result.get("sources", [])
        answer = self._answer_with_fallback_citations(str(result["answer"]), sources)
        session = self._get_or_create_session(user_id, notebook_id)
        session_id = str(session["id"])
        self._insert_message(session_id, "user", message.strip(), [])
        self._insert_message(session_id, "assistant", answer, sources)
        self._touch_chat_session(session_id)
        self._touch_notebook(user_id, notebook_id)
        messages = self._messages(session_id)
        return {
            "session_id": session_id,
            "messages": messages,
            "answer": answer,
            "sources": sources,
            "strategy": result.get("strategy"),
            "strategy_reasoning": result.get("strategy_reasoning"),
        }

    def begin_chat_message(
        self,
        user_id: str,
        notebook_id: str,
        message: str,
        document_names: list[str],
    ) -> dict[str, Any]:
        """Validate and persist the user side of a streaming chat message."""
        self._require_notebook(user_id, notebook_id)
        selected_documents = self._validate_completed_documents(user_id, notebook_id, document_names)
        clean_message = message.strip()

        session = self._get_or_create_session(user_id, notebook_id)
        session_id = str(session["id"])
        self._insert_message(session_id, "user", clean_message, [])
        self._touch_chat_session(session_id)
        self._touch_notebook(user_id, notebook_id)

        return {
            "session_id": session_id,
            "message": clean_message,
            "document_names": selected_documents,
        }

    def finalize_chat_message(
        self,
        user_id: str,
        notebook_id: str,
        session_id: str,
        answer: str,
        sources: list[dict[str, Any]],
        strategy: str | None = None,
        strategy_reasoning: str | None = None,
    ) -> dict[str, Any]:
        """Persist the assistant side of a streaming chat message."""
        self._require_notebook(user_id, notebook_id)
        final_answer = self._answer_with_fallback_citations(answer, sources)

        self._insert_message(session_id, "assistant", final_answer, sources)
        self._touch_chat_session(session_id)
        self._touch_notebook(user_id, notebook_id)
        messages = self._messages(session_id)
        return {
            "session_id": session_id,
            "messages": messages,
            "answer": final_answer,
            "sources": sources,
            "strategy": strategy,
            "strategy_reasoning": strategy_reasoning,
        }

    def list_notes(self, user_id: str, notebook_id: str) -> list[NotebookNote]:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("notebook_notes")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        return [self._note(row) for row in rows]

    def create_note(
        self,
        user_id: str,
        notebook_id: str,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        document_names: list[str],
    ) -> NotebookNote:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("notebook_notes")
            .insert(
                {
                    "notebook_id": notebook_id,
                    "user_id": user_id,
                    "question": question.strip(),
                    "answer": answer.strip(),
                    "sources": sources,
                    "document_names": document_names,
                }
            )
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookValidationError("Note could not be saved.")
        self._touch_notebook(user_id, notebook_id)
        return self._note(row)

    def update_note(
        self,
        user_id: str,
        notebook_id: str,
        note_id: str,
        question: str,
    ) -> NotebookNote:
        self._require_note(user_id, notebook_id, note_id)
        clean_question = question.strip()
        if not clean_question:
            raise NotebookValidationError("Note title is required.")

        result = (
            self.client.table("notebook_notes")
            .update({"question": clean_question, "updated_at": _utc_now()})
            .eq("id", note_id)
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookValidationError("Note could not be updated.")
        self._touch_notebook(user_id, notebook_id)
        return self._note(row)

    def delete_note(self, user_id: str, notebook_id: str, note_id: str) -> None:
        self._require_note(user_id, notebook_id, note_id)
        (
            self.client.table("notebook_notes")
            .delete()
            .eq("id", note_id)
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        self._touch_notebook(user_id, notebook_id)

    def _source_counts(self, user_id: str) -> dict[str, int]:
        result = (
            self.client.table("document_processing_status")
            .select("notebook_id,document_name")
            .eq("user_id", user_id)
            .eq("status", ProcessingStatus.COMPLETED)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        counts: dict[str, set[str]] = {}
        for row in rows:
            notebook_id = str(row.get("notebook_id"))
            counts.setdefault(notebook_id, set()).add(str(row.get("document_name")))
        return {notebook_id: len(names) for notebook_id, names in counts.items()}

    def _require_notebook(self, user_id: str, notebook_id: str) -> dict[str, Any]:
        result = (
            self.client.table("notebooks")
            .select("*")
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookNotFoundError("Notebook not found.")
        return row

    def _require_document_status(self, user_id: str, notebook_id: str, document_name: str) -> dict[str, Any]:
        row = self._document_status_row(user_id, notebook_id, document_name)
        if not row:
            raise NotebookNotFoundError("Source not found.")
        return row

    def _document_status_row(self, user_id: str, notebook_id: str, document_name: str) -> dict[str, Any] | None:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("document_processing_status")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .eq("document_name", document_name)
            .limit(1)
            .execute()
        )
        return _first(result.data)

    def _require_note(self, user_id: str, notebook_id: str, note_id: str) -> dict[str, Any]:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("notebook_notes")
            .select("*")
            .eq("id", note_id)
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookNotFoundError("Note not found.")
        return row

    def _get_or_create_session(self, user_id: str, notebook_id: str) -> dict[str, Any]:
        self._require_notebook(user_id, notebook_id)
        result = (
            self.client.table("chat_sessions")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        row = _first(result.data)
        return row if row else self._create_session(user_id, notebook_id)

    def _create_session(self, user_id: str, notebook_id: str) -> dict[str, Any]:
        result = (
            self.client.table("chat_sessions")
            .insert({"notebook_id": notebook_id, "user_id": user_id, "title": "Current chat"})
            .execute()
        )
        row = _first(result.data)
        if not row:
            raise NotebookValidationError("Chat session could not be created.")
        return row

    def _insert_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: list[dict[str, Any]],
    ) -> None:
        (
            self.client.table("chat_messages")
            .insert({"session_id": session_id, "role": role, "content": content, "sources": sources})
            .execute()
        )

    def _messages(self, session_id: str) -> list[ChatMessageOut]:
        result = (
            self.client.table("chat_messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        return [
            ChatMessageOut(
                id=str(row["id"]),
                role=row["role"],
                content=row["content"],
                sources=row.get("sources") or [],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def _validate_completed_documents(
        self,
        user_id: str,
        notebook_id: str,
        document_names: list[str],
    ) -> list[str]:
        unique_names = list(dict.fromkeys(name.strip() for name in document_names if name.strip()))
        if not unique_names:
            raise NotebookValidationError("Select at least one completed document before chatting.")

        result = (
            self.client.table("document_processing_status")
            .select("document_name,status")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .in_("document_name", unique_names)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        completed = {str(row["document_name"]) for row in rows if row.get("status") == ProcessingStatus.COMPLETED}
        missing = [name for name in unique_names if name not in completed]
        if missing:
            raise NotebookValidationError(f"These documents are not ready for chat: {', '.join(missing)}")
        return unique_names

    def _auto_title_from_first_upload(
        self,
        user_id: str,
        notebook_id: str,
        notebook: dict[str, Any],
        document_name: str,
    ) -> None:
        title = str(notebook.get("title") or "").strip()
        if title and title.lower() != "untitled notebook":
            return

        existing = (
            self.client.table("document_processing_status")
            .select("id")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if isinstance(existing.data, list) and existing.data:
            return

        (
            self.client.table("notebooks")
            .update({"title": document_name, "updated_at": _utc_now()})
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        logger.info(
            "Auto-renamed first-upload notebook notebook_id=%s user_id=%s title=%s",
            notebook_id,
            user_id,
            document_name,
        )

    def _answer_with_fallback_citations(self, answer: str, sources: list[dict[str, Any]]) -> str:
        if not sources or CITATION_PATTERN.search(answer):
            return answer

        citation_count = min(len(sources), 3)
        citations = " ".join(f"[{index}]" for index in range(1, citation_count + 1))
        logger.info("RAG answer had no [N] citations; appended fallback citations=%s", citations)
        return f"{answer.rstrip()}\n\nNguồn: {citations}"

    def _touch_notebook(self, user_id: str, notebook_id: str) -> None:
        (
            self.client.table("notebooks")
            .update({"updated_at": _utc_now()})
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )

    def _touch_chat_session(self, session_id: str) -> None:
        self.client.table("chat_sessions").update({"updated_at": _utc_now()}).eq("id", session_id).execute()

    def _invalidate_document_cache(self, notebook_id: str, document_name: str) -> None:
        try:
            invalidate_document_caches(notebook_id, document_name)
        except Exception:
            logger.info(
                "Could not invalidate Gemini cache notebook_id=%s document=%s.",
                notebook_id,
                document_name,
                exc_info=True,
            )

    def _clean_document_title(self, value: str) -> str:
        clean_value = normalize_document_name(value)
        for extension in (".pdf", ".docx"):
            if clean_value.lower().endswith(extension):
                clean_value = normalize_document_name(clean_value[: -len(extension)])
                break
        return clean_value

    def _default_storage_paths_for_document(self, user_id: str, notebook_id: str, document_name: str) -> list[str]:
        return [
            f"{user_id}/{notebook_id}/{safe_pdf_storage_path(document_name)}",
            f"{user_id}/{notebook_id}/{document_name}.pdf",
        ]

    def _storage_paths_for_document(self, user_id: str, notebook_id: str, document_name: str) -> list[str]:
        paths = self._default_storage_paths_for_document(user_id, notebook_id, document_name)
        result = (
            self.client.table("documents")
            .select("metadata")
            .eq("notebook_id", notebook_id)
            .eq("document_name", document_name)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        for row in rows:
            metadata = row.get("metadata") if isinstance(row, dict) else None
            if isinstance(metadata, dict) and isinstance(metadata.get("storage_path"), str):
                paths.append(metadata["storage_path"])
        return list(dict.fromkeys(paths))

    def _storage_paths_for_notebook(self, user_id: str, notebook_id: str) -> list[str]:
        paths: list[str] = []
        statuses = (
            self.client.table("document_processing_status")
            .select("document_name")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for row in (statuses.data if isinstance(statuses.data, list) else []):
            document_name = row.get("document_name") if isinstance(row, dict) else None
            if isinstance(document_name, str) and document_name:
                paths.extend(self._default_storage_paths_for_document(user_id, notebook_id, document_name))

        documents = (
            self.client.table("documents")
            .select("document_name,metadata")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for row in (documents.data if isinstance(documents.data, list) else []):
            if not isinstance(row, dict):
                continue

            document_name = row.get("document_name")
            if isinstance(document_name, str) and document_name:
                paths.extend(self._default_storage_paths_for_document(user_id, notebook_id, document_name))

            metadata = row.get("metadata")
            if isinstance(metadata, dict) and isinstance(metadata.get("storage_path"), str):
                paths.append(metadata["storage_path"])

        return list(dict.fromkeys(paths))

    def _delete_storage_paths(self, storage_paths: list[str]) -> None:
        self._remove_storage_paths("pdfs", storage_paths, "source PDFs")

    def _audio_storage_paths_for_notebook(self, user_id: str, notebook_id: str) -> list[str]:
        result = (
            self.client.table("audio_overviews")
            .select("id,status,storage_path,metadata")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        paths: list[str] = []
        for row in (result.data if isinstance(result.data, list) else []):
            if not isinstance(row, dict):
                continue

            storage_path = row.get("storage_path")
            if isinstance(storage_path, str) and storage_path:
                paths.append(storage_path)
                continue

            overview_id = row.get("id")
            if row.get("status") == "completed" and overview_id:
                paths.append(f"{user_id}/{notebook_id}/{overview_id}.m4a")

        return list(dict.fromkeys(paths))

    def _delete_audio_storage_paths(self, storage_paths: list[str]) -> None:
        if not storage_paths:
            return

        self._remove_storage_paths(get_settings().audio_overview_bucket, storage_paths, "audio overviews")

    def _remove_storage_paths(self, bucket_name: str, storage_paths: list[str], label: str) -> None:
        storage = getattr(self.client, "storage", None)
        if not storage or not storage_paths:
            return

        unique_paths = list(dict.fromkeys(storage_paths))
        for index in range(0, len(unique_paths), STORAGE_REMOVE_BATCH_SIZE):
            batch = unique_paths[index : index + STORAGE_REMOVE_BATCH_SIZE]
            try:
                storage.from_(bucket_name).remove(batch)
            except Exception:
                logger.info("Could not remove one or more %s from storage.", label, exc_info=True)

    def _revoke_notebook_tasks(self, user_id: str, notebook_id: str) -> None:
        statuses = (
            self.client.table("document_processing_status")
            .select("task_id")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for source in (statuses.data if isinstance(statuses.data, list) else []):
            if isinstance(source, dict):
                self._revoke_processing_task(source)

        audio_overviews = (
            self.client.table("audio_overviews")
            .select("metadata")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for overview in (audio_overviews.data if isinstance(audio_overviews.data, list) else []):
            metadata = overview.get("metadata") if isinstance(overview, dict) else None
            task_id = metadata.get("task_id") if isinstance(metadata, dict) else None
            if isinstance(task_id, str) and task_id:
                self._revoke_task(task_id, "audio overview")

    def _revoke_processing_task(self, source: dict[str, Any]) -> None:
        task_id = str(source.get("task_id") or "").strip()
        if not task_id:
            return

        self._revoke_task(task_id, "document processing")

    def _revoke_task(self, task_id: str, label: str) -> None:
        try:
            settings = get_settings()
            self._celery_app(settings.redis_url).control.revoke(task_id, terminate=True)
        except Exception:
            logger.info("Could not revoke %s task task_id=%s.", label, task_id, exc_info=True)

    def _celery_app(self, redis_url: str) -> Celery:
        return Celery("datn_backend_control", broker=redis_url, backend=redis_url)

    def _rename_document_references(
        self,
        user_id: str,
        notebook_id: str,
        current_name: str,
        next_name: str,
    ) -> None:
        notes = (
            self.client.table("notebook_notes")
            .select("id,document_names,sources")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for note in (notes.data if isinstance(notes.data, list) else []):
            updates: dict[str, Any] = {}
            document_names = note.get("document_names") if isinstance(note, dict) else None
            if isinstance(document_names, list):
                renamed_names = [next_name if name == current_name else name for name in document_names]
                if renamed_names != document_names:
                    updates["document_names"] = renamed_names

            sources = note.get("sources") if isinstance(note, dict) else None
            renamed_sources, sources_changed = self._rename_sources(sources, current_name, next_name)
            if sources_changed:
                updates["sources"] = renamed_sources

            if updates:
                updates["updated_at"] = _utc_now()
                self.client.table("notebook_notes").update(updates).eq("id", note["id"]).execute()

        sessions = (
            self.client.table("chat_sessions")
            .select("id")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for session in (sessions.data if isinstance(sessions.data, list) else []):
            session_id = session.get("id") if isinstance(session, dict) else None
            if not session_id:
                continue

            messages = self.client.table("chat_messages").select("id,sources").eq("session_id", session_id).execute()
            for message in (messages.data if isinstance(messages.data, list) else []):
                sources = message.get("sources") if isinstance(message, dict) else None
                renamed_sources, sources_changed = self._rename_sources(sources, current_name, next_name)
                if sources_changed:
                    self.client.table("chat_messages").update({"sources": renamed_sources}).eq("id", message["id"]).execute()

        audio_overviews = (
            self.client.table("audio_overviews")
            .select("id,metadata")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )
        for overview in (audio_overviews.data if isinstance(audio_overviews.data, list) else []):
            metadata = overview.get("metadata") if isinstance(overview, dict) else None
            if not isinstance(metadata, dict):
                continue
            overview_id = overview.get("id")
            if not overview_id:
                continue

            document_names = metadata.get("document_names")
            if not isinstance(document_names, list):
                continue

            renamed_names = [next_name if name == current_name else name for name in document_names]
            if renamed_names == document_names:
                continue

            self.client.table("audio_overviews").update(
                {
                    "metadata": {**metadata, "document_names": renamed_names},
                    "updated_at": _utc_now(),
                }
            ).eq("id", overview_id).execute()

    def _rename_sources(self, sources: Any, current_name: str, next_name: str) -> tuple[list[Any], bool]:
        if not isinstance(sources, list):
            return [], False

        changed = False
        renamed_sources: list[Any] = []
        for source in sources:
            if isinstance(source, dict) and source.get("document") == current_name:
                renamed_source = dict(source)
                renamed_source["document"] = next_name
                renamed_sources.append(renamed_source)
                changed = True
            else:
                renamed_sources.append(source)

        return renamed_sources, changed

    def _delete_local_upload(self, user_id: str, notebook_id: str, document_name: str) -> None:
        try:
            settings = get_settings()
            upload_dir = Path(settings.uploads_dir) / user_id / notebook_id
            for extension in (".pdf", ".docx"):
                file_path = upload_dir / safe_document_storage_path(document_name, extension)
                if file_path.exists():
                    file_path.unlink()
        except Exception:
            logger.info("Could not remove local uploaded document.", exc_info=True)

    def _rename_local_upload(
        self,
        user_id: str,
        notebook_id: str,
        current_name: str,
        next_name: str,
    ) -> None:
        try:
            settings = get_settings()
            upload_dir = Path(settings.uploads_dir) / user_id / notebook_id
            for extension in (".pdf", ".docx"):
                current_path = upload_dir / safe_document_storage_path(current_name, extension)
                next_path = upload_dir / safe_document_storage_path(next_name, extension)
                if current_path.exists() and not next_path.exists():
                    current_path.rename(next_path)
        except Exception:
            logger.info("Could not rename local uploaded document.", exc_info=True)

    def _summary(self, row: dict[str, Any], source_count: int) -> NotebookSummary:
        return NotebookSummary(
            id=str(row["id"]),
            title=str(row["title"]),
            description=row.get("description"),
            source_count=source_count,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _document_status(self, row: dict[str, Any]) -> DocumentStatus:
        return DocumentStatus(
            id=str(row["id"]) if row.get("id") else None,
            document_name=str(row["document_name"]),
            status=row["status"],
            total_chunks=row.get("total_chunks"),
            processed_chunks=row.get("processed_chunks"),
            error_message=row.get("error_message"),
            created_at=str(row["created_at"]) if row.get("created_at") else None,
            updated_at=str(row["updated_at"]) if row.get("updated_at") else None,
        )

    def _note(self, row: dict[str, Any]) -> NotebookNote:
        return NotebookNote(
            id=str(row["id"]),
            question=str(row["question"]),
            answer=str(row["answer"]),
            sources=row.get("sources") or [],
            document_names=row.get("document_names") or [],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def get_notebook_workspace_service(supabase_client: Any) -> NotebookWorkspaceService:
    """Factory for notebook workspace services."""
    return NotebookWorkspaceService(supabase_client)
