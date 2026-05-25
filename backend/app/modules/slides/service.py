"""Service layer for notebook slide decks."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from celery import Celery

from app.core.config import get_settings
from app.modules.slides.repository import SlideDeckRepository, first, get_slide_deck_repository, utc_now
from app.modules.slides.schemas import SlideDeckOut


class SlideDeckNotFoundError(ValueError):
    """Raised when a slide deck or notebook cannot be found."""


class SlideDeckValidationError(ValueError):
    """Raised when a slide deck request is invalid."""


class SlideDeckService:
    """Authenticated slide deck workflows."""

    def __init__(self, client: Any):
        self.client = client
        self.repository: SlideDeckRepository = get_slide_deck_repository(client)

    def list_slide_decks(self, user_id: str, notebook_id: str) -> list[SlideDeckOut]:
        self._require_notebook(user_id, notebook_id)
        return [self._deck(row) for row in self.repository.list_by_notebook(user_id, notebook_id)]

    def create_slide_deck(
        self,
        user_id: str,
        notebook_id: str,
        document_names: list[str],
    ) -> SlideDeckOut:
        self._require_notebook(user_id, notebook_id)
        selected_documents = self._validate_completed_documents(user_id, notebook_id, document_names)

        settings = get_settings()
        task_id = str(uuid4())
        row = self.repository.create_pending(
            notebook_id=notebook_id,
            user_id=user_id,
            task_id=task_id,
            document_names=selected_documents,
        )
        deck_id = str(row["id"])

        try:
            self._celery_app(settings.redis_url).send_task(
                "app.modules.slides.tasks.generate_slide_deck_task",
                args=[deck_id, notebook_id, user_id, selected_documents],
                queue="slides",
                task_id=task_id,
            )
            self._touch_notebook(user_id, notebook_id)
        except Exception as exc:
            self.repository.update_status(deck_id, "failed", {"error_message": str(exc)})
            raise

        return self._deck(row)

    def get_pdf_url(
        self,
        user_id: str,
        notebook_id: str,
        deck_id: str,
        expires_in: int = 3600,
    ) -> str:
        row = self._require_slide_deck(user_id, notebook_id, deck_id)
        if row.get("status") != "completed" or not row.get("storage_path"):
            raise SlideDeckValidationError("Slide deck PDF is not ready yet.")

        result = (
            self.client.storage.from_(get_settings().slide_deck_bucket)
            .create_signed_url(str(row["storage_path"]), expires_in)
        )
        if isinstance(result, dict):
            signed_url = (
                result.get("signedURL")
                or result.get("signed_url")
                or result.get("signedUrl")
                or result.get("url")
            )
            if signed_url:
                return str(signed_url)

        signed_url = getattr(result, "signed_url", None) or getattr(result, "signedURL", None)
        if signed_url:
            return str(signed_url)

        raise SlideDeckValidationError("Could not create a signed slide deck URL.")

    def delete_slide_deck(self, user_id: str, notebook_id: str, deck_id: str) -> None:
        row = self._require_slide_deck(user_id, notebook_id, deck_id)
        task_id = self._metadata(row).get("task_id")
        if isinstance(task_id, str) and task_id:
            self._revoke_processing_task(task_id)

        storage_path = row.get("storage_path")
        if isinstance(storage_path, str) and storage_path:
            try:
                self.client.storage.from_(get_settings().slide_deck_bucket).remove([storage_path])
            except Exception:
                pass

        self.repository.delete(deck_id)
        self._touch_notebook(user_id, notebook_id)

    def _require_notebook(self, user_id: str, notebook_id: str) -> dict[str, Any]:
        result = (
            self.client.table("notebooks")
            .select("*")
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        row = first(result.data)
        if not row:
            raise SlideDeckNotFoundError("Notebook not found.")
        return row

    def _require_slide_deck(self, user_id: str, notebook_id: str, deck_id: str) -> dict[str, Any]:
        self._require_notebook(user_id, notebook_id)
        row = self.repository.get_owned(user_id, notebook_id, deck_id)
        if not row:
            raise SlideDeckNotFoundError("Slide deck not found.")
        return row

    def _validate_completed_documents(
        self,
        user_id: str,
        notebook_id: str,
        document_names: list[str],
    ) -> list[str]:
        unique_names = list(dict.fromkeys(name.strip() for name in document_names if name.strip()))
        if not unique_names:
            raise SlideDeckValidationError("Select at least one completed document before creating a presentation.")

        result = (
            self.client.table("document_processing_status")
            .select("document_name,status")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .in_("document_name", unique_names)
            .execute()
        )
        rows = result.data if isinstance(result.data, list) else []
        completed = {str(row["document_name"]) for row in rows if row.get("status") == "completed"}
        missing = [name for name in unique_names if name not in completed]
        if missing:
            raise SlideDeckValidationError(f"These documents are not ready for presentation: {', '.join(missing)}")
        return unique_names

    def _touch_notebook(self, user_id: str, notebook_id: str) -> None:
        (
            self.client.table("notebooks")
            .update({"updated_at": utc_now()})
            .eq("id", notebook_id)
            .eq("user_id", user_id)
            .execute()
        )

    def _revoke_processing_task(self, task_id: str) -> None:
        try:
            settings = get_settings()
            self._celery_app(settings.redis_url).control.revoke(task_id, terminate=True)
        except Exception:
            pass

    def _celery_app(self, redis_url: str) -> Celery:
        return Celery("datn_slide_deck_control", broker=redis_url, backend=redis_url)

    def _deck(self, row: dict[str, Any]) -> SlideDeckOut:
        metadata = self._metadata(row)
        document_names = metadata.get("document_names")
        if not isinstance(document_names, list):
            document_names = []
        source_count = metadata.get("source_count")
        if not isinstance(source_count, int):
            source_count = len(document_names)

        deck_json = metadata.get("deck_json")
        return SlideDeckOut(
            id=str(row["id"]),
            notebook_id=str(row["notebook_id"]),
            status=row["status"],
            storage_path=row.get("storage_path"),
            title=str(metadata.get("title") or "Presentation"),
            deck_json=deck_json if isinstance(deck_json, dict) else None,
            document_names=[str(name) for name in document_names],
            source_count=source_count,
            content_type=metadata.get("content_type"),
            error_message=metadata.get("error_message"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _metadata(row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata")
        return metadata if isinstance(metadata, dict) else {}


def get_slide_deck_service(client: Any) -> SlideDeckService:
    """Return a slide deck service."""
    return SlideDeckService(client)
