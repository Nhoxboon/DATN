"""Supabase repository for audio overview records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def first(data: Any) -> dict[str, Any] | None:
    """Return the first row from a Supabase response payload."""
    return data[0] if isinstance(data, list) and data else None


class AudioOverviewRepository:
    """Repository for the public.audio_overviews table."""

    def __init__(self, client: Any):
        self.client = client

    def list_by_notebook(self, user_id: str, notebook_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("audio_overviews")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data if isinstance(result.data, list) else []

    def get(self, overview_id: str) -> dict[str, Any] | None:
        result = self.client.table("audio_overviews").select("*").eq("id", overview_id).limit(1).execute()
        return first(result.data)

    def get_owned(self, user_id: str, notebook_id: str, overview_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("audio_overviews")
            .select("*")
            .eq("id", overview_id)
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return first(result.data)

    def create_pending(
        self,
        *,
        notebook_id: str,
        user_id: str,
        task_id: str,
        document_names: list[str],
    ) -> dict[str, Any]:
        metadata = {
            "document_names": document_names,
            "task_id": task_id,
            "title": "Audio Overview",
            "content_type": "audio/mp4",
            "error_message": None,
        }
        result = (
            self.client.table("audio_overviews")
            .insert(
                {
                    "notebook_id": notebook_id,
                    "user_id": user_id,
                    "storage_path": None,
                    "status": "pending",
                    "metadata": metadata,
                }
            )
            .execute()
        )
        row = first(result.data)
        if not row:
            raise ValueError("Audio overview could not be created.")
        return row

    def update_status(
        self,
        overview_id: str,
        status: str,
        metadata_updates: dict[str, Any] | None = None,
        storage_path: str | None = None,
    ) -> dict[str, Any]:
        row = self.get(overview_id)
        if not row:
            raise ValueError("Audio overview not found.")

        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        next_metadata = {**metadata, **(metadata_updates or {})}
        updates: dict[str, Any] = {
            "status": status,
            "metadata": next_metadata,
            "updated_at": utc_now(),
        }
        if storage_path is not None:
            updates["storage_path"] = storage_path

        result = self.client.table("audio_overviews").update(updates).eq("id", overview_id).execute()
        updated = first(result.data)
        return updated or {**row, **updates}

    def delete(self, overview_id: str) -> None:
        self.client.table("audio_overviews").delete().eq("id", overview_id).execute()


def get_audio_overview_repository(client: Any) -> AudioOverviewRepository:
    """Return an audio overview repository."""
    return AudioOverviewRepository(client)
