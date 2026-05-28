"""Tests for the audio overview module."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
import unittest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "service-key")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GOOGLE_API_KEY", "google-key")

from app.modules.audio_overviews.service import (
    AudioOverviewValidationError,
    AudioOverviewService,
)
from app.modules.audio_overviews.tasks import (
    _coerce_audio_bytes,
    _normalize_script_speaker_labels,
    _parse_json_object,
    _require_min_duration,
)
from app.modules.audio_overviews.tasks import generate_audio_overview_task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeQuery:
    def __init__(self, client: "FakeSupabaseClient", table_name: str):
        self.client = client
        self.table_name = table_name
        self.operation = "select"
        self.payload: dict[str, object] | list[dict[str, object]] | None = None
        self.filters: list[tuple[str, str, object]] = []
        self.order_key: str | None = None
        self.order_desc = False
        self.limit_count: int | None = None

    def select(self, *_args: object) -> "FakeQuery":
        self.operation = "select"
        return self

    def insert(self, payload: dict[str, object] | list[dict[str, object]]) -> "FakeQuery":
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload: dict[str, object]) -> "FakeQuery":
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.operation = "delete"
        return self

    def eq(self, key: str, value: object) -> "FakeQuery":
        self.filters.append(("eq", key, value))
        return self

    def in_(self, key: str, values: list[object]) -> "FakeQuery":
        self.filters.append(("in", key, values))
        return self

    def order(self, key: str, desc: bool = False) -> "FakeQuery":
        self.order_key = key
        self.order_desc = desc
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def execute(self) -> SimpleNamespace:
        if self.operation == "insert":
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            inserted = [self.client.insert_row(self.table_name, row or {}) for row in rows]
            return SimpleNamespace(data=inserted)

        rows = self._filtered_rows()

        if self.operation == "update":
            assert isinstance(self.payload, dict)
            for row in rows:
                row.update(self.payload)
            return SimpleNamespace(data=[row.copy() for row in rows])

        if self.operation == "delete":
            self.client.delete_rows(self.table_name, rows)
            return SimpleNamespace(data=[row.copy() for row in rows])

        if self.order_key:
            rows.sort(key=lambda row: str(row.get(self.order_key) or ""), reverse=self.order_desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return SimpleNamespace(data=[row.copy() for row in rows])

    def _filtered_rows(self) -> list[dict[str, object]]:
        rows = list(self.client.tables.get(self.table_name, []))
        for op, key, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(key) == value]
            elif op == "in":
                rows = [row for row in rows if row.get(key) in value]
        return rows


class FakeStorageBucket:
    def __init__(self):
        self.removed: list[str] = []

    def create_signed_url(self, path: str, _expires_in: int) -> dict[str, str]:
        return {"signedURL": f"https://signed.example/{path}"}

    def remove(self, paths: list[str]) -> None:
        self.removed.extend(paths)


class FakeStorage:
    def __init__(self):
        self.bucket = FakeStorageBucket()

    def from_(self, _bucket_name: str) -> FakeStorageBucket:
        return self.bucket


class FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, list[dict[str, object]]] = {
            "notebooks": [],
            "document_processing_status": [],
            "audio_overviews": [],
        }
        self.storage = FakeStorage()

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def insert_row(self, table_name: str, row: dict[str, object]) -> dict[str, object]:
        stored = dict(row)
        stored.setdefault("id", str(uuid4()))
        stored.setdefault("created_at", _now())
        stored.setdefault("updated_at", _now())
        self.tables[table_name].append(stored)
        return stored.copy()

    def delete_rows(self, table_name: str, rows: list[dict[str, object]]) -> None:
        ids = {row.get("id") for row in rows}
        self.tables[table_name] = [row for row in self.tables[table_name] if row.get("id") not in ids]


class AudioOverviewServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeSupabaseClient()
        self.service = AudioOverviewService(self.client)
        self.client.insert_row(
            "notebooks",
            {
                "id": "notebook-1",
                "user_id": "user-1",
                "title": "Research notebook",
                "description": None,
            },
        )
        self.client.insert_row(
            "document_processing_status",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "document_name": "doc-a",
                "status": "completed",
            },
        )

    def test_create_audio_overview_queues_worker_task(self) -> None:
        fake_celery = SimpleNamespace(send_task=Mock())
        with patch(
            "app.modules.audio_overviews.service.get_settings",
            return_value=SimpleNamespace(redis_url="redis://test"),
        ), patch.object(self.service, "_celery_app", return_value=fake_celery):
            overview = self.service.create_audio_overview("user-1", "notebook-1", ["doc-a"])

        self.assertEqual(overview.status, "pending")
        self.assertEqual(overview.document_names, ["doc-a"])
        self.assertEqual(len(self.client.tables["audio_overviews"]), 1)
        fake_celery.send_task.assert_called_once()
        self.assertEqual(fake_celery.send_task.call_args.kwargs["queue"], "audio_overviews")

    def test_create_rejects_unready_documents(self) -> None:
        with self.assertRaises(AudioOverviewValidationError):
            self.service.create_audio_overview("user-1", "notebook-1", ["missing"])

    def test_create_requires_selected_documents(self) -> None:
        with self.assertRaises(AudioOverviewValidationError):
            self.service.create_audio_overview("user-1", "notebook-1", [])

    def test_signed_url_requires_completed_audio(self) -> None:
        overview = self.client.insert_row(
            "audio_overviews",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "status": "completed",
                "storage_path": "user-1/notebook-1/audio.m4a",
                "metadata": {"title": "Audio Overview"},
            },
        )

        with patch(
            "app.modules.audio_overviews.service.get_settings",
            return_value=SimpleNamespace(audio_overview_bucket="audio-overviews", redis_url="redis://test"),
        ):
            signed_url = self.service.get_audio_url("user-1", "notebook-1", str(overview["id"]))

        self.assertIn("audio.m4a", signed_url)

    def test_delete_removes_storage_object_and_row(self) -> None:
        overview = self.client.insert_row(
            "audio_overviews",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "status": "completed",
                "storage_path": "user-1/notebook-1/audio.m4a",
                "metadata": {"task_id": "task-1"},
            },
        )

        with patch(
            "app.modules.audio_overviews.service.get_settings",
            return_value=SimpleNamespace(audio_overview_bucket="audio-overviews", redis_url="redis://test"),
        ), patch.object(self.service, "_celery_app", return_value=SimpleNamespace(control=SimpleNamespace(revoke=Mock()))):
            self.service.delete_audio_overview("user-1", "notebook-1", str(overview["id"]))

        self.assertEqual(self.client.tables["audio_overviews"], [])
        self.assertEqual(self.client.storage.bucket.removed, ["user-1/notebook-1/audio.m4a"])


class AudioOverviewTaskHelperTests(unittest.TestCase):
    def test_parse_json_object_accepts_fenced_json(self) -> None:
        payload = _parse_json_object('```json\n{"title": "Audio", "script_text": "Host: hi"}\n```')

        self.assertEqual(payload["title"], "Audio")
        self.assertEqual(payload["script_text"], "Host: hi")

    def test_coerce_audio_bytes_decodes_base64(self) -> None:
        self.assertEqual(_coerce_audio_bytes("YWJj"), b"abc")
        self.assertEqual(_coerce_audio_bytes(b"abc"), b"abc")

    def test_require_min_duration_rejects_short_audio(self) -> None:
        with self.assertRaisesRegex(ValueError, "shorter than the required minimum"):
            _require_min_duration(42.5, 150)

    def test_require_min_duration_allows_disabled_minimum(self) -> None:
        _require_min_duration(0.0, 0)

    def test_normalize_script_speaker_labels_removes_persona_names(self) -> None:
        script = "Minh: Mở đầu.\nLan: Đúng vậy, Minh. Nội dung chính."

        normalized = _normalize_script_speaker_labels(
            script,
            "podcast_dialogue",
            ["Minh", "Lan"],
            ["Speaker A", "Speaker B"],
            ["Narrator"],
        )

        self.assertIn("Speaker A: Mở đầu.", normalized)
        self.assertIn("Speaker B: Đúng vậy. Nội dung chính.", normalized)
        self.assertNotIn("Minh:", normalized)
        self.assertNotIn("Lan:", normalized)
        self.assertNotIn("Đúng vậy, Minh", normalized)

    def test_task_skips_when_overview_was_deleted_before_worker_start(self) -> None:
        client = FakeSupabaseClient()

        with patch(
            "app.modules.audio_overviews.tasks.get_settings",
            return_value=SimpleNamespace(audio_overview_bucket="audio-overviews"),
        ), patch("app.modules.audio_overviews.tasks.get_supabase_client", return_value=client), patch(
            "app.modules.audio_overviews.tasks.get_app_config"
        ) as get_app_config, patch("app.modules.audio_overviews.tasks.genai.Client") as genai_client:
            result = generate_audio_overview_task.run("missing-overview", "notebook-1", "user-1", ["doc-a"])

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "missing")
        get_app_config.assert_not_called()
        genai_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
