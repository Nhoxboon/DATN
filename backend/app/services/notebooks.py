"""Notebook workspace service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.document_naming import document_name_from_filename
from app.db.processing_status import ProcessingStatus, get_processing_status_repository
from app.db.repository import get_document_repository
from app.schemas.notebooks import (
    ChatMessageOut,
    DocumentStatus,
    NotebookDetail,
    NotebookNote,
    NotebookSummary,
)
from app.services.documents import get_document_service


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
        (
            self.client.table("notebooks")
            .delete()
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )

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
        self._require_notebook(user_id, notebook_id)
        document_name = document_name_from_filename(filename)
        status_repo = get_processing_status_repository(self.client)
        status_repo.create_status(
            notebook_id=notebook_id,
            user_id=user_id,
            document_name=document_name,
            task_id="sync-upload",
        )
        status_repo.update_status(notebook_id, document_name, ProcessingStatus.PROCESSING)

        try:
            service = get_document_service()
            result = service.upload_from_bytes(
                notebook_id=notebook_id,
                user_id=user_id,
                file_content=file_content,
                filename=filename,
                document_name=document_name,
            )
            chunks_processed = int(result["chunks_processed"])
            status_repo.update_status(
                notebook_id,
                document_name,
                ProcessingStatus.COMPLETED,
                processed_chunks=chunks_processed,
                total_chunks=chunks_processed,
            )
            self._touch_notebook(user_id, notebook_id)
            return result
        except Exception as exc:
            status_repo.update_status(
                notebook_id,
                document_name,
                ProcessingStatus.FAILED,
                error_message=str(exc),
            )
            raise

    def delete_document(self, user_id: str, notebook_id: str, document_name: str) -> None:
        self._require_notebook(user_id, notebook_id)
        service = get_document_service()
        service.delete_document(notebook_id, user_id, document_name)
        get_processing_status_repository(self.client).delete_status(notebook_id, document_name)
        self._touch_notebook(user_id, notebook_id)

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
        session = self._get_or_create_session(user_id, notebook_id)
        session_id = str(session["id"])
        self._insert_message(session_id, "user", message.strip(), [])
        self._insert_message(session_id, "assistant", str(result["answer"]), result.get("sources", []))
        self._touch_chat_session(session_id)
        self._touch_notebook(user_id, notebook_id)
        messages = self._messages(session_id)
        return {
            "session_id": session_id,
            "messages": messages,
            "answer": str(result["answer"]),
            "sources": result.get("sources", []),
            "strategy": result.get("strategy"),
            "strategy_reasoning": result.get("strategy_reasoning"),
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
