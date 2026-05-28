"""Supabase repository for generated slide deck records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """Return an ISO UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def first(data: Any) -> dict[str, Any] | None:
    """Return the first row from a Supabase response payload."""
    return data[0] if isinstance(data, list) and data else None


class SlideDeckRepository:
    """Repository for the public.slides table."""

    def __init__(self, client: Any):
        self.client = client

    def list_by_notebook(self, user_id: str, notebook_id: str) -> list[dict[str, Any]]:
        result = (
            self.client.table("slides")
            .select("*")
            .eq("notebook_id", notebook_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data if isinstance(result.data, list) else []

    def get(self, deck_id: str) -> dict[str, Any] | None:
        result = self.client.table("slides").select("*").eq("id", deck_id).limit(1).execute()
        return first(result.data)

    def get_owned(self, user_id: str, notebook_id: str, deck_id: str) -> dict[str, Any] | None:
        result = (
            self.client.table("slides")
            .select("*")
            .eq("id", deck_id)
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
            "source_count": len(document_names),
            "task_id": task_id,
            "title": "Presentation",
            "deck_json": None,
            "content_type": "application/pdf",
            "error_message": None,
        }
        result = (
            self.client.table("slides")
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
            raise ValueError("Slide deck could not be created.")
        return row

    def update_status(
        self,
        deck_id: str,
        status: str,
        metadata_updates: dict[str, Any] | None = None,
        storage_path: str | None = None,
    ) -> dict[str, Any]:
        row = self.get(deck_id)
        if not row:
            raise ValueError("Slide deck not found.")

        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        next_metadata = {**metadata, **(metadata_updates or {})}
        updates: dict[str, Any] = {
            "status": status,
            "metadata": next_metadata,
            "updated_at": utc_now(),
        }
        if storage_path is not None:
            updates["storage_path"] = storage_path

        result = self.client.table("slides").update(updates).eq("id", deck_id).execute()
        updated = first(result.data)
        return updated or {**row, **updates}

    def delete(self, deck_id: str) -> None:
        self.client.table("slides").delete().eq("id", deck_id).execute()


def get_slide_deck_repository(client: Any) -> SlideDeckRepository:
    """Return a slide deck repository."""
    return SlideDeckRepository(client)
