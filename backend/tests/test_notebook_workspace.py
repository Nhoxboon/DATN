"""Tests for notebook workspace service."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
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


class FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, list[dict[str, object]]] = {
            "notebooks": [],
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

    def test_ownership_is_enforced(self) -> None:
        with self.assertRaises(NotebookNotFoundError):
            self.service.get_notebook("other-user", "notebook-1")

    def test_current_chat_reloads_until_new_chat_clears_it(self) -> None:
        session_id, messages = self.service.get_current_chat("user-1", "notebook-1")
        self.assertEqual(messages, [])

        self.service._insert_message(session_id, "user", "What is PDP8?", [])
        reloaded_session_id, reloaded_messages = self.service.get_current_chat("user-1", "notebook-1")

        self.assertEqual(reloaded_session_id, session_id)
        self.assertEqual(len(reloaded_messages), 1)
        self.assertEqual(reloaded_messages[0].content, "What is PDP8?")

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
        self.assertEqual(result["answer"], "Indexed answer")
        self.assertEqual(len(result["messages"]), 2)

    def test_selected_documents_must_be_completed(self) -> None:
        self.add_document("ready")
        self.add_document("still-indexing", ProcessingStatus.PROCESSING)

        with self.assertRaises(NotebookValidationError):
            self.service._validate_completed_documents(
                "user-1",
                "notebook-1",
                ["ready", "still-indexing", "missing"],
            )

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


if __name__ == "__main__":
    unittest.main()
