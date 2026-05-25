"""Tests for the slide deck module."""

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

from app.modules.slides.service import SlideDeckService, SlideDeckValidationError
from app.modules.slides.tasks import (
    SlideDeckPayload,
    _materialize_visuals,
    _parse_json_object,
    _visual_candidates,
    generate_slide_deck_task,
)


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
            "slides": [],
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


class SlideDeckServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeSupabaseClient()
        self.service = SlideDeckService(self.client)
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

    def test_create_slide_deck_queues_worker_task(self) -> None:
        fake_celery = SimpleNamespace(send_task=Mock())
        with patch(
            "app.modules.slides.service.get_settings",
            return_value=SimpleNamespace(redis_url="redis://test"),
        ), patch.object(self.service, "_celery_app", return_value=fake_celery):
            deck = self.service.create_slide_deck("user-1", "notebook-1", ["doc-a"])

        self.assertEqual(deck.status, "pending")
        self.assertEqual(deck.document_names, ["doc-a"])
        self.assertEqual(deck.source_count, 1)
        self.assertEqual(len(self.client.tables["slides"]), 1)
        fake_celery.send_task.assert_called_once()
        self.assertEqual(fake_celery.send_task.call_args.kwargs["queue"], "slides")

    def test_create_rejects_unready_documents(self) -> None:
        with self.assertRaises(SlideDeckValidationError):
            self.service.create_slide_deck("user-1", "notebook-1", ["missing"])

    def test_create_requires_selected_documents(self) -> None:
        with self.assertRaises(SlideDeckValidationError):
            self.service.create_slide_deck("user-1", "notebook-1", [])

    def test_signed_url_requires_completed_pdf(self) -> None:
        deck = self.client.insert_row(
            "slides",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "status": "completed",
                "storage_path": "user-1/notebook-1/deck.pdf",
                "metadata": {"title": "Presentation", "source_count": 1, "document_names": ["doc-a"]},
            },
        )

        with patch(
            "app.modules.slides.service.get_settings",
            return_value=SimpleNamespace(slide_deck_bucket="slide-decks", redis_url="redis://test"),
        ):
            signed_url = self.service.get_pdf_url("user-1", "notebook-1", str(deck["id"]))

        self.assertIn("deck.pdf", signed_url)

    def test_delete_removes_storage_object_and_row(self) -> None:
        deck = self.client.insert_row(
            "slides",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "status": "completed",
                "storage_path": "user-1/notebook-1/deck.pdf",
                "metadata": {"task_id": "task-1"},
            },
        )

        with patch(
            "app.modules.slides.service.get_settings",
            return_value=SimpleNamespace(slide_deck_bucket="slide-decks", redis_url="redis://test"),
        ), patch.object(self.service, "_celery_app", return_value=SimpleNamespace(control=SimpleNamespace(revoke=Mock()))):
            self.service.delete_slide_deck("user-1", "notebook-1", str(deck["id"]))

        self.assertEqual(self.client.tables["slides"], [])
        self.assertEqual(self.client.storage.bucket.removed, ["user-1/notebook-1/deck.pdf"])


class SlideDeckTaskHelperTests(unittest.TestCase):
    def test_parse_json_object_accepts_fenced_json(self) -> None:
        payload = _parse_json_object('```json\n{"title": "Deck", "slide_count": 5, "slides": []}\n```')

        self.assertEqual(payload["title"], "Deck")

    def test_deck_validation_enforces_slide_count_and_concise_text(self) -> None:
        valid_slides = [
            {
                "slide_number": index,
                "layout_type": "KEY_BULLETS" if index % 2 else "SUMMARY",
                "title": f"Slide {index}",
                "bullets": ["Core idea only"],
                "content": {},
                "visual": {"kind": "none"},
            }
            for index in range(1, 6)
        ]

        deck = SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": valid_slides})

        self.assertEqual(deck.slide_count, 5)

        invalid = dict(valid_slides[0])
        invalid["bullets"] = ["word " * 21]
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": [invalid, *valid_slides[1:]]})

    def test_deck_validation_rejects_visible_citations(self) -> None:
        slides = [
            {
                "slide_number": index,
                "layout_type": "KEY_BULLETS" if index % 2 else "SUMMARY",
                "title": "Finding [1]" if index == 1 else f"Slide {index}",
                "bullets": ["Core idea"],
                "content": {},
                "visual": {"kind": "none"},
            }
            for index in range(1, 6)
        ]

        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": slides})

    def test_visual_candidates_extract_visual_source_pages(self) -> None:
        candidates = _visual_candidates(
            [
                {
                    "document_name": "doc-a",
                    "page_range": "3-4",
                    "pages": [3, 4],
                    "metadata": {"has_visual": True, "storage_path": "user/notebook/doc.pdf"},
                },
                {"document_name": "doc-b", "page_range": "1", "metadata": {"has_visual": False}},
            ]
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["page"], 3)

    def test_materialize_visuals_caps_generated_images(self) -> None:
        deck = {
            "title": "Deck",
            "slides": [
                {"slide_number": index, "title": f"Slide {index}", "visual": {"kind": "generated_image", "prompt": "x"}}
                for index in range(1, 9)
            ],
        }

        with patch("app.modules.slides.tasks._generate_image_data_url", return_value="data:image/jpeg;base64,abc"):
            result = _materialize_visuals(
                deck=deck,
                genai_client=Mock(),
                image_model="gemini-2.5-flash-image",
                client=Mock(),
                settings=SimpleNamespace(uploads_dir="/tmp"),
                user_id="user-1",
                notebook_id="notebook-1",
                visual_candidates=[],
            )

        generated = [
            slide["visual"]
            for slide in result["slides"]
            if slide["visual"].get("kind") == "generated_image" and slide["visual"].get("data_url")
        ]
        self.assertEqual(len(generated), 2)
        self.assertEqual(result["image_generation_count"], 2)

    def test_task_skips_when_deck_was_deleted_before_worker_start(self) -> None:
        client = FakeSupabaseClient()

        with patch(
            "app.modules.slides.tasks.get_settings",
            return_value=SimpleNamespace(slide_deck_bucket="slide-decks"),
        ), patch("app.modules.slides.tasks.get_supabase_client", return_value=client), patch(
            "app.modules.slides.tasks.get_app_config"
        ) as get_app_config, patch("app.modules.slides.tasks.genai.Client") as genai_client:
            result = generate_slide_deck_task.run("missing-deck", "notebook-1", "user-1", ["doc-a"])

        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "missing")
        get_app_config.assert_not_called()
        genai_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
