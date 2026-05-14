"""Tests for notebook workspace service."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch
from uuid import uuid4

from app.db.processing_status import ProcessingStatus
from app.services.notebooks import (
    NotebookNotFoundError,
    NotebookValidationError,
    NotebookWorkspaceService,
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

    def upsert(self, payload: dict[str, object], on_conflict: str | None = None) -> "FakeQuery":
        self.operation = "upsert"
        self.payload = payload
        if on_conflict:
            for key in on_conflict.split(","):
                self.filters.append(("conflict", key.strip(), payload.get(key.strip())))
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

        if self.operation == "upsert":
            assert isinstance(self.payload, dict)
            conflict_filters = [item for item in self.filters if item[0] == "conflict"]
            rows = list(self.client.tables.get(self.table_name, []))
            for row in rows:
                if conflict_filters and all(row.get(key) == value for _, key, value in conflict_filters):
                    row.update(self.payload)
                    return SimpleNamespace(data=[row.copy()])
            inserted = self.client.insert_row(self.table_name, self.payload)
            return SimpleNamespace(data=[inserted])

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


class FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, list[dict[str, object]]] = {
            "notebooks": [],
            "documents": [],
            "document_processing_status": [],
            "chat_sessions": [],
            "chat_messages": [],
            "notebook_notes": [],
        }

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

        if table_name == "chat_sessions":
            self.tables["chat_messages"] = [
                row for row in self.tables["chat_messages"] if row.get("session_id") not in ids
            ]


class FakeRAGService:
    def __init__(self):
        self.seen: dict[str, object] | None = None

    def query(self, **kwargs: object) -> dict[str, object]:
        self.seen = kwargs
        return {
            "answer": "Indexed answer",
            "sources": [{"document": "doc-a", "page_range": "1-2", "similarity": 0.9}],
            "strategy": "single-hop",
            "strategy_reasoning": "test",
        }


class NotebookWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeSupabaseClient()
        self.service = NotebookWorkspaceService(self.client)
        self.invalidate_patcher = patch("app.services.notebooks.invalidate_document_caches")
        self.invalidate_patcher.start()
        self.addCleanup(self.invalidate_patcher.stop)
        self.notebook = self.client.insert_row(
            "notebooks",
            {
                "id": "notebook-1",
                "user_id": "user-1",
                "title": "Research notebook",
                "description": None,
            },
        )

    def add_document(self, document_name: str, status: str = ProcessingStatus.COMPLETED) -> None:
        self.client.insert_row(
            "document_processing_status",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "document_name": document_name,
                "status": status,
                "total_chunks": 2,
                "processed_chunks": 2 if status == ProcessingStatus.COMPLETED else 0,
                "error_message": None,
            },
        )

    def add_chunk(self, document_name: str) -> None:
        self.client.insert_row(
            "documents",
            {
                "notebook_id": "notebook-1",
                "user_id": "user-1",
                "document_name": document_name,
                "chunk_id": 1,
                "content": "Chunk text",
                "metadata": {"storage_path": f"user-1/notebook-1/{document_name}.pdf"},
            },
        )

    def test_ownership_is_enforced(self) -> None:
        with self.assertRaises(NotebookNotFoundError):
            self.service.get_notebook("other-user", "notebook-1")

    def test_first_upload_auto_renames_untitled_notebook(self) -> None:
        notebook = self.client.insert_row(
            "notebooks",
            {
                "id": "notebook-untitled",
                "user_id": "user-1",
                "title": "Untitled Notebook",
                "description": None,
            },
        )

        self.service._auto_title_from_first_upload(
            "user-1",
            "notebook-untitled",
            notebook,
            "State Machine Diagram",
        )

        renamed = self.service.get_notebook("user-1", "notebook-untitled")
        self.assertEqual(renamed.title, "State Machine Diagram")

    def test_first_upload_does_not_override_existing_title(self) -> None:
        self.service._auto_title_from_first_upload(
            "user-1",
            "notebook-1",
            self.notebook,
            "State Machine Diagram",
        )

        unchanged = self.service.get_notebook("user-1", "notebook-1")
        self.assertEqual(unchanged.title, "Research notebook")

    def test_upload_rejects_non_worker_mode_without_sync_status(self) -> None:
        with patch(
            "app.services.notebooks.get_settings",
            return_value=SimpleNamespace(document_processing_mode="sync", uploads_dir="/tmp", redis_url="redis://test"),
        ):
            with self.assertRaises(NotebookValidationError):
                self.service.upload_document("user-1", "notebook-1", b"%PDF-1.4", "State Machine Diagram.pdf")

        statuses = self.client.tables["document_processing_status"]
        self.assertFalse(any(row.get("task_id") == "sync-upload" for row in statuses))

    def test_upload_always_queues_worker_task(self) -> None:
        fake_celery = SimpleNamespace(send_task=Mock())

        with TemporaryDirectory() as uploads_dir:
            with patch(
                "app.services.notebooks.get_settings",
                return_value=SimpleNamespace(
                    document_processing_mode="worker",
                    uploads_dir=uploads_dir,
                    redis_url="redis://test",
                ),
            ), patch.object(self.service, "_celery_app", return_value=fake_celery):
                result = self.service.upload_document(
                    "user-1",
                    "notebook-1",
                    b"%PDF-1.4",
                    "State Machine Diagram.pdf",
                )

        statuses = self.client.tables["document_processing_status"]
        self.assertTrue(result["queued"])
        self.assertEqual(result["chunks_processed"], 0)
        self.assertEqual(len(statuses), 1)
        self.assertNotEqual(statuses[0]["task_id"], "sync-upload")
        fake_celery.send_task.assert_called_once()

    def test_upload_invalidates_normalized_document_cache_before_queueing(self) -> None:
        fake_celery = SimpleNamespace(send_task=Mock())

        with TemporaryDirectory() as uploads_dir:
            with patch(
                "app.services.notebooks.get_settings",
                return_value=SimpleNamespace(
                    document_processing_mode="worker",
                    uploads_dir=uploads_dir,
                    redis_url="redis://test",
                ),
            ), patch.object(self.service, "_celery_app", return_value=fake_celery), patch(
                "app.services.notebooks.invalidate_document_caches"
            ) as invalidate:
                self.service.upload_document(
                    "user-1",
                    "notebook-1",
                    b"%PDF-1.4",
                    "State Machine Diagram.pdf",
                )

        invalidate.assert_called_once_with("notebook-1", "State Machine Diagram")

    def test_current_chat_reloads_until_new_chat_clears_it(self) -> None:
        session_id, messages = self.service.get_current_chat("user-1", "notebook-1")
        self.assertEqual(messages, [])

        self.service._insert_message(session_id, "user", "What does this document say?", [])
        reloaded_session_id, reloaded_messages = self.service.get_current_chat("user-1", "notebook-1")

        self.assertEqual(reloaded_session_id, session_id)
        self.assertEqual(len(reloaded_messages), 1)
        self.assertEqual(reloaded_messages[0].content, "What does this document say?")

        new_session_id, new_messages = self.service.new_chat("user-1", "notebook-1")

        self.assertNotEqual(new_session_id, session_id)
        self.assertEqual(new_messages, [])
        self.assertEqual(self.service.get_current_chat("user-1", "notebook-1")[1], [])

    def test_send_chat_passes_notebook_and_selected_documents_to_rag(self) -> None:
        self.add_document("doc-a")
        self.add_document("doc-b")
        rag_service = FakeRAGService()

        with patch("app.services.rag.dependencies.get_rag_service", return_value=rag_service):
            result = self.service.send_chat_message("user-1", "notebook-1", "Compare them", ["doc-a", "doc-b"])

        self.assertEqual(rag_service.seen["notebook_id"], "notebook-1")
        self.assertEqual(rag_service.seen["doc_names"], ["doc-a", "doc-b"])
        self.assertEqual(result["answer"], "Indexed answer\n\nNguồn: [1]")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][1].content, "Indexed answer\n\nNguồn: [1]")

    def test_stream_chat_begin_and_finalize_persists_messages(self) -> None:
        self.add_document("doc-a")

        prepared = self.service.begin_chat_message("user-1", "notebook-1", " What changed? ", ["doc-a"])
        result = self.service.finalize_chat_message(
            "user-1",
            "notebook-1",
            str(prepared["session_id"]),
            "Streamed answer [1]",
            [{"document": "doc-a", "page_range": "1", "similarity": 0.9}],
            "cached-single-hop",
            "manifest citations",
        )

        self.assertEqual(prepared["message"], "What changed?")
        self.assertEqual(prepared["document_names"], ["doc-a"])
        self.assertEqual(result["answer"], "Streamed answer [1]")
        self.assertEqual(result["strategy"], "cached-single-hop")
        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(result["messages"][0].role, "user")
        self.assertEqual(result["messages"][1].role, "assistant")
        self.assertEqual(result["messages"][1].sources[0]["document"], "doc-a")

    def test_selected_documents_must_be_completed(self) -> None:
        self.add_document("ready")
        self.add_document("still-indexing", ProcessingStatus.PROCESSING)

        with self.assertRaises(NotebookValidationError):
            self.service._validate_completed_documents(
                "user-1",
                "notebook-1",
                ["ready", "still-indexing", "missing"],
            )

    def test_rename_document_updates_status_and_chunks(self) -> None:
        self.add_document("Old source")
        self.add_chunk("Old source")

        renamed = self.service.rename_document("user-1", "notebook-1", "Old source", "New source.pdf")

        self.assertEqual(renamed.documents[0].document_name, "New source")
        self.assertEqual(self.client.tables["document_processing_status"][0]["document_name"], "New source")
        self.assertEqual(self.client.tables["documents"][0]["document_name"], "New source")

    def test_rename_document_invalidates_old_and_new_cache_names(self) -> None:
        self.add_document("Old source")
        self.add_chunk("Old source")

        with patch("app.services.notebooks.invalidate_document_caches") as invalidate:
            self.service.rename_document("user-1", "notebook-1", "Old source", "New source.pdf")

        self.assertEqual(
            invalidate.call_args_list,
            [
                call("notebook-1", "Old source"),
                call("notebook-1", "New source"),
            ],
        )

    def test_rename_document_updates_saved_note_and_chat_sources(self) -> None:
        self.add_document("Old source")
        self.add_chunk("Old source")
        self.service.create_note(
            "user-1",
            "notebook-1",
            "Question?",
            "Saved answer",
            [{"document": "Old source"}],
            ["Old source"],
        )
        session_id, _ = self.service.get_current_chat("user-1", "notebook-1")
        self.service._insert_message(session_id, "assistant", "Answer", [{"document": "Old source"}])

        self.service.rename_document("user-1", "notebook-1", "Old source", "New source")

        note = self.service.list_notes("user-1", "notebook-1")[0]
        messages = self.service._messages(session_id)
        self.assertEqual(note.document_names, ["New source"])
        self.assertEqual(note.sources[0]["document"], "New source")
        self.assertEqual(messages[0].sources[0]["document"], "New source")

    def test_rename_document_rejects_duplicate_name(self) -> None:
        self.add_document("Existing")
        self.add_document("Taken")

        with self.assertRaises(NotebookValidationError):
            self.service.rename_document("user-1", "notebook-1", "Existing", "Taken")

    def test_delete_document_removes_status_even_without_chunks(self) -> None:
        self.add_document("Queued source", ProcessingStatus.PENDING)

        self.service.delete_document("user-1", "notebook-1", "Queued source")
        self.service.delete_document("user-1", "notebook-1", "Queued source")

        self.assertEqual(self.client.tables["document_processing_status"], [])

    def test_delete_document_removes_chunks(self) -> None:
        self.add_document("Indexed source")
        self.add_chunk("Indexed source")

        self.service.delete_document("user-1", "notebook-1", "Indexed source")

        self.assertEqual(self.client.tables["document_processing_status"], [])
        self.assertEqual(self.client.tables["documents"], [])

    def test_delete_document_invalidates_existing_document_cache_only(self) -> None:
        self.add_document("Indexed source")
        self.add_chunk("Indexed source")

        with patch("app.services.notebooks.invalidate_document_caches") as invalidate:
            self.service.delete_document("user-1", "notebook-1", "Indexed source")
            self.service.delete_document("user-1", "notebook-1", "Indexed source")

        invalidate.assert_called_once_with("notebook-1", "Indexed source")

    def test_create_note_persists_saved_answer_without_touching_chat(self) -> None:
        session_id, _ = self.service.get_current_chat("user-1", "notebook-1")
        self.service._insert_message(session_id, "assistant", "Temporary answer", [])

        note = self.service.create_note(
            "user-1",
            "notebook-1",
            "Question?",
            "Saved answer",
            [{"document": "doc-a"}],
            ["doc-a"],
        )

        notes = self.service.list_notes("user-1", "notebook-1")
        _, messages = self.service.new_chat("user-1", "notebook-1")

        self.assertEqual(note.question, "Question?")
        self.assertEqual(len(notes), 1)
        self.assertEqual(messages, [])
        self.assertEqual(self.service.list_notes("user-1", "notebook-1")[0].answer, "Saved answer")

    def test_update_note_renames_saved_note(self) -> None:
        note = self.service.create_note("user-1", "notebook-1", "Original title", "Saved answer", [], [])

        renamed = self.service.update_note("user-1", "notebook-1", note.id, "Renamed title")

        self.assertEqual(renamed.question, "Renamed title")
        self.assertEqual(self.service.list_notes("user-1", "notebook-1")[0].question, "Renamed title")

    def test_delete_note_removes_saved_note(self) -> None:
        note = self.service.create_note("user-1", "notebook-1", "Question?", "Saved answer", [], [])

        self.service.delete_note("user-1", "notebook-1", note.id)

        self.assertEqual(self.service.list_notes("user-1", "notebook-1"), [])


if __name__ == "__main__":
    unittest.main()
