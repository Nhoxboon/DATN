"""Service layer for notebook audio overviews."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from celery import Celery

from app.core.config import get_settings
from app.modules.audio_overviews.repository import AudioOverviewRepository, get_audio_overview_repository, first, utc_now
from app.modules.audio_overviews.schemas import AudioOverviewOut


class AudioOverviewNotFoundError(ValueError):
    """Raised when an audio overview or notebook cannot be found."""


class AudioOverviewValidationError(ValueError):
    """Raised when an audio overview request is invalid."""


class AudioOverviewService:
    """Authenticated audio overview workflows."""

    def __init__(self, client: Any):
        self.client = client
        self.repository: AudioOverviewRepository = get_audio_overview_repository(client)

    def list_audio_overviews(self, user_id: str, notebook_id: str) -> list[AudioOverviewOut]:
        self._require_notebook(user_id, notebook_id)
        return [self._overview(row) for row in self.repository.list_by_notebook(user_id, notebook_id)]

    def create_audio_overview(
        self,
        user_id: str,
        notebook_id: str,
        document_names: list[str],
    ) -> AudioOverviewOut:
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
        overview_id = str(row["id"])

        try:
            self._celery_app(settings.redis_url).send_task(
                "app.modules.audio_overviews.tasks.generate_audio_overview_task",
                args=[overview_id, notebook_id, user_id, selected_documents],
                queue="audio_overviews",
                task_id=task_id,
            )
            self._touch_notebook(user_id, notebook_id)
        except Exception as exc:
            row = self.repository.update_status(
                overview_id,
                "failed",
                {"error_message": str(exc)},
            )
            raise

        return self._overview(row)

    def get_audio_url(
        self,
        user_id: str,
        notebook_id: str,
        overview_id: str,
        expires_in: int = 3600,
    ) -> str:
        row = self._require_audio_overview(user_id, notebook_id, overview_id)
        if row.get("status") != "completed" or not row.get("storage_path"):
            raise AudioOverviewValidationError("Audio overview is not ready yet.")

        result = (
            self.client.storage.from_(get_settings().audio_overview_bucket)
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

        raise AudioOverviewValidationError("Could not create a signed audio URL.")

    def delete_audio_overview(self, user_id: str, notebook_id: str, overview_id: str) -> None:
        row = self._require_audio_overview(user_id, notebook_id, overview_id)
        task_id = self._metadata(row).get("task_id")
        if isinstance(task_id, str) and task_id:
            self._revoke_processing_task(task_id)

        storage_path = row.get("storage_path")
        if isinstance(storage_path, str) and storage_path:
            try:
                self.client.storage.from_(get_settings().audio_overview_bucket).remove([storage_path])
            except Exception:
                pass

        self.repository.delete(overview_id)
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
            raise AudioOverviewNotFoundError("Notebook not found.")
        return row

    def _require_audio_overview(self, user_id: str, notebook_id: str, overview_id: str) -> dict[str, Any]:
        self._require_notebook(user_id, notebook_id)
        row = self.repository.get_owned(user_id, notebook_id, overview_id)
        if not row:
            raise AudioOverviewNotFoundError("Audio overview not found.")
        return row

    def _validate_completed_documents(
        self,
        user_id: str,
        notebook_id: str,
        document_names: list[str],
    ) -> list[str]:
        unique_names = list(dict.fromkeys(name.strip() for name in document_names if name.strip()))
        if not unique_names:
            raise AudioOverviewValidationError("Select at least one completed document before creating audio.")

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
            raise AudioOverviewValidationError(f"These documents are not ready for audio: {', '.join(missing)}")
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
        return Celery("datn_audio_overview_control", broker=redis_url, backend=redis_url)

    def _overview(self, row: dict[str, Any]) -> AudioOverviewOut:
        metadata = self._metadata(row)
        return AudioOverviewOut(
            id=str(row["id"]),
            notebook_id=str(row["notebook_id"]),
            status=row["status"],
            storage_path=row.get("storage_path"),
            title=str(metadata.get("title") or "Audio Overview"),
            style=metadata.get("style"),
            script_text=metadata.get("script_text"),
            document_names=metadata.get("document_names") if isinstance(metadata.get("document_names"), list) else [],
            duration_seconds=metadata.get("duration_seconds"),
            content_type=metadata.get("content_type"),
            error_message=metadata.get("error_message"),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _metadata(row: dict[str, Any]) -> dict[str, Any]:
        metadata = row.get("metadata")
        return metadata if isinstance(metadata, dict) else {}


def get_audio_overview_service(client: Any) -> AudioOverviewService:
    """Return an audio overview service."""
    return AudioOverviewService(client)
