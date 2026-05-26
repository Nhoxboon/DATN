"""Tests for the slide deck module."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
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
    StoryOutlinePayload,
    _materialize_visuals,
    _parse_json_object,
    _repair_deck_payload,
    _slide_visible_word_count,
    _render_deck_pdf_for_config,
    _visual_candidates,
    generate_slide_deck_task,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _v2_slide(index: int, layout: str, title: str | None = None, components: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "slide_number": index,
        "layout_type": layout,
        "title": title or f"Slide {index}",
        "subtitle": None,
        "bullets": [],
        "components": components or {},
        "content": {},
        "visual": {"kind": "none"},
    }


def _card(card_id: str, heading: str = "Core", desc: str = "Short action cue") -> dict[str, str]:
    return {"id": card_id, "tag": "INSIGHT", "icon_key": "cpu", "heading": heading, "desc": desc}


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
            _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
            _v2_slide(2, "GRID_COMPOSITE", components={"cards": [_card("01"), _card("02"), _card("03")]}),
            _v2_slide(
                3,
                "PROCESS_FLOW_WITH_CALLOUT",
                components={
                    "flow_steps": [
                        {"step": "1", "label": "Start", "action": "Load settings"},
                        {"step": "2", "label": "Select locale", "action": "Set locale"},
                        {"step": "3", "label": "Load table", "action": "Lazy load Addressables"},
                    ],
                    "callout_box": {"type": "INSIGHT", "text": "Lazy loading keeps startup memory stable."},
                },
            ),
            _v2_slide(
                4,
                "METRIC_DASHBOARD",
                components={
                    "metrics": [
                        {"icon_key": "cpu", "value": "CPU", "label": "Script budget", "context": "Profile hot paths"},
                        {"icon_key": "gauge", "value": "FPS", "label": "Frame target", "context": "Avoid spikes"},
                        {"icon_key": "database", "value": "RAM", "label": "Memory load", "context": "Use pooling"},
                    ]
                },
            ),
            _v2_slide(
                5,
                "CHECKLIST",
                title="Preflight Checklist",
                components={
                    "checklist": [
                        {"icon_key": "check", "text": "Pool repeated objects"},
                        {"icon_key": "check", "text": "Profile physics cost"},
                        {"icon_key": "check", "text": "Lazy load localization tables"},
                        {"icon_key": "check", "text": "Run pseudo-localization tests"},
                    ]
                },
            ),
        ]

        deck = SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": valid_slides})

        self.assertEqual(deck.slide_count, 5)

        invalid = dict(valid_slides[0])
        invalid["components"] = {"cards": [_card("01", desc="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen")]}
        invalid["layout_type"] = "GRID_COMPOSITE"
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": [invalid, *valid_slides[1:]]})

    def test_deck_validation_rejects_visible_citations(self) -> None:
        slides = [
            _v2_slide(1, "TITLE_HERO", title="Finding [1]", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
            _v2_slide(2, "GRID_COMPOSITE", components={"cards": [_card("01"), _card("02"), _card("03")]}),
            _v2_slide(3, "DUAL_PILLARS", components={"cards": [_card("01"), _card("02")]}),
            _v2_slide(
                4,
                "METRIC_DASHBOARD",
                components={
                    "metrics": [
                        {"icon_key": "cpu", "value": "CPU", "label": "Script budget", "context": "Profile paths"},
                        {"icon_key": "gauge", "value": "FPS", "label": "Frame target", "context": "Avoid spikes"},
                        {"icon_key": "database", "value": "RAM", "label": "Memory load", "context": "Use pooling"},
                    ]
                },
            ),
            _v2_slide(5, "GRID_COMPOSITE", title="Architecture", components={"cards": [_card("01"), _card("02"), _card("03")]}),
        ]

        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": slides})

    def test_deck_validation_rejects_final_summary_slide(self) -> None:
        slides = [
            _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
            _v2_slide(2, "GRID_COMPOSITE", components={"cards": [_card("01"), _card("02"), _card("03")]}),
            _v2_slide(3, "DUAL_PILLARS", components={"cards": [_card("01"), _card("02")]}),
            _v2_slide(4, "GRID_COMPOSITE", components={"cards": [_card("01"), _card("02"), _card("03")]}),
            _v2_slide(5, "CHECKLIST", title="Tom tat", components={"checklist": [{"icon_key": "check", "text": "Run final checks"}] * 4}),
        ]

        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": slides})

    def test_outline_requires_transition_for_multiple_topics(self) -> None:
        slides = [
            {"slide_number": 1, "chapter": "Optimization", "layout_type": "TITLE_HERO", "title": "Optimization", "purpose": "Open", "visual_strategy": "icon"},
            {"slide_number": 2, "chapter": "Optimization", "layout_type": "GRID_COMPOSITE", "title": "CPU", "purpose": "Explain", "visual_strategy": "icon"},
            {"slide_number": 3, "chapter": "Optimization", "layout_type": "PROCESS_FLOW_WITH_CALLOUT", "title": "Flow", "purpose": "Explain", "visual_strategy": "icon"},
            {"slide_number": 4, "chapter": "Localization", "layout_type": "GRID_COMPOSITE", "title": "Localization", "purpose": "Shift", "visual_strategy": "icon"},
            {"slide_number": 5, "chapter": "Localization", "layout_type": "CHECKLIST", "title": "Preflight", "purpose": "Action", "visual_strategy": "icon"},
        ]
        with self.assertRaises(ValueError):
            StoryOutlinePayload.model_validate({"title": "Deck", "slide_count": 5, "chapters": ["Optimization", "Localization"], "slides": slides})

    def test_deck_validation_rejects_missing_anchors_invalid_icon_and_bad_process_actions(self) -> None:
        missing_anchors = [
            _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
            _v2_slide(2, "CODE_COMPARISON", components={"comparison": [{"label": "Loop", "left": "Instantiate", "right": "Pool"}, {"label": "Load", "left": "Eager", "right": "Lazy"}]}),
            _v2_slide(3, "PROCESS_FLOW_WITH_CALLOUT", components={"flow_steps": [{"step": "1", "label": "Start", "action": "Load settings"}, {"step": "2", "label": "Choose", "action": "Set locale"}, {"step": "3", "label": "Load", "action": "Lazy load table"}], "callout_box": {"type": "INSIGHT", "text": "Load only what is needed."}}),
            _v2_slide(4, "CODE_COMPARISON", components={"comparison": [{"label": "CPU", "left": "Find", "right": "Cache"}, {"label": "Physics", "left": "Default", "right": "Limit"}]}),
            _v2_slide(5, "CODE_COMPARISON", components={"comparison": [{"label": "RAM", "left": "New", "right": "Reuse"}, {"label": "UI", "left": "Always", "right": "Batch"}]}),
        ]
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": missing_anchors})

        invalid_icon = _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "not-real", "caption": "Main idea"}})
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": [invalid_icon, *missing_anchors[1:]]})

        bad_process = _v2_slide(
            3,
            "PROCESS_FLOW_WITH_CALLOUT",
            components={
                "flow_steps": [
                    {"step": "1", "label": "Game Start", "action": "SelectedLocale được thiết lập theo hệ thống và người chơi"},
                    {"step": "2", "label": "Load Table", "action": "Lazy load Addressables"},
                    {"step": "3", "label": "Update UI", "action": "Bind translated text"},
                ],
                "callout_box": {"type": "WARNING", "text": "Avoid loading all tables at startup."},
            },
        )
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": [missing_anchors[0], missing_anchors[1], bad_process, *missing_anchors[3:]]})

        duplicate_visuals = [
            _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "source_page", "source_index": 1, "page": 3, "caption": "Diagram"}}),
            _v2_slide(2, "VISUAL_ANCHOR", components={"visual_anchor": {"kind": "source_page", "source_index": 1, "page": 3, "caption": "Same diagram"}}),
            _v2_slide(3, "GRID_COMPOSITE", components={"cards": [_card("01"), _card("02"), _card("03")]}),
            _v2_slide(4, "DUAL_PILLARS", components={"cards": [_card("01"), _card("02")]}),
            _v2_slide(5, "CHECKLIST", title="Preflight", components={"checklist": [{"icon_key": "check", "text": "Run final checks"}] * 4}),
        ]
        with self.assertRaises(ValueError):
            SlideDeckPayload.model_validate({"title": "Deck", "slide_count": 5, "slides": duplicate_visuals})

    def test_repair_deck_payload_trims_verbose_component_text(self) -> None:
        payload = {
            "title": "Deck",
            "slide_count": 5,
            "slides": [
                _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
                _v2_slide(
                    2,
                    "GRID_COMPOSITE",
                    components={
                        "cards": [
                            _card("01", desc="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen"),
                            _card("02", desc="Một mô tả khá dài để Gemini lỡ viết quá số lượng từ cho phép trong card này."),
                            _card("03"),
                        ]
                    },
                ),
                _v2_slide(
                    3,
                    "PROCESS_FLOW_WITH_CALLOUT",
                    components={
                        "flow_steps": [
                            {"step": "1", "label": "Game Start", "action": "Load settings"},
                            {"step": "2", "label": "Select Locale", "action": "Thiết lập ngôn ngữ hệ thống"},
                            {"step": "3", "label": "Update UI", "action": "Cập nhật giao diện người dùng bằng dữ liệu bản dịch mới nhất."},
                        ],
                        "callout_box": {"type": "WARNING", "text": "Avoid loading all tables at startup."},
                    },
                ),
                _v2_slide(
                    4,
                    "METRIC_DASHBOARD",
                    components={
                        "metrics": [
                            {"icon_key": "cpu", "value": "CPU", "label": "Script budget", "context": "Profile hot paths"},
                            {"icon_key": "gauge", "value": "FPS", "label": "Frame target", "context": "Avoid spikes"},
                            {"icon_key": "database", "value": "RAM", "label": "Memory load", "context": "Use pooling"},
                        ]
                    },
                ),
                _v2_slide(
                    5,
                    "CHECKLIST",
                    title="Preflight Checklist",
                    components={"checklist": [{"icon_key": "check", "text": "Run final checks"}] * 4},
                ),
            ],
        }

        repaired = _repair_deck_payload(payload)
        deck = SlideDeckPayload.model_validate(repaired)

        self.assertEqual(deck.slide_count, 5)
        self.assertLessEqual(len(deck.slides[1].components.cards[0].desc.split()), 16)
        self.assertEqual(deck.slides[2].components.flow_steps[2].action, "Cập nhật giao diện người dùng bằng dữ liệu bản dịch mới.")

    def test_repair_deck_payload_enforces_total_slide_word_budget(self) -> None:
        payload = {
            "title": "Deck",
            "slide_count": 5,
            "slides": [
                _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
                _v2_slide(
                    2,
                    "GRID_COMPOSITE",
                    title="Một tiêu đề kỹ thuật dài nhằm kiểm tra ngân sách chữ toàn slide",
                    components={
                        "cards": [
                            _card("01", "Bước thiết lập locale runtime", "Chọn ngôn ngữ hệ thống và đồng bộ trạng thái giao diện khi người dùng đổi locale."),
                            _card("02", "Bảng dữ liệu dịch thuật", "Tải String Table bằng Addressables để giảm tải bộ nhớ lúc khởi động."),
                            _card("03", "Kiểm thử pseudo localization", "Phát hiện chuỗi hardcode và lỗi tràn giao diện trước khi phát hành."),
                        ]
                    },
                )
                | {
                    "bullets": ["Đây là phần legacy không render trong layout V2 và phải bị bỏ khỏi payload."],
                    "content": {"caption": "Legacy content dài không xuất hiện ở renderer nhưng từng làm validator đếm quá ngân sách chữ."},
                },
                _v2_slide(3, "DUAL_PILLARS", components={"cards": [_card("01"), _card("02")]}),
                _v2_slide(
                    4,
                    "METRIC_DASHBOARD",
                    components={
                        "metrics": [
                            {"icon_key": "cpu", "value": "CPU", "label": "Script budget", "context": "Profile hot paths"},
                            {"icon_key": "gauge", "value": "FPS", "label": "Frame target", "context": "Avoid spikes"},
                            {"icon_key": "database", "value": "RAM", "label": "Memory load", "context": "Use pooling"},
                        ]
                    },
                ),
                _v2_slide(5, "CHECKLIST", title="Preflight Checklist", components={"checklist": [{"icon_key": "check", "text": "Run final checks"}] * 4}),
            ],
        }

        repaired = _repair_deck_payload(payload)
        deck = SlideDeckPayload.model_validate(repaired)

        self.assertEqual(deck.slide_count, 5)
        self.assertLessEqual(_slide_visible_word_count(repaired["slides"][1]), 70)
        self.assertEqual(repaired["slides"][1]["bullets"], [])
        self.assertEqual(repaired["slides"][1]["content"], {})

    def test_repair_deck_payload_removes_image_visuals_from_non_visual_layouts(self) -> None:
        payload = {
            "title": "Deck",
            "slide_count": 5,
            "slides": [
                _v2_slide(1, "TITLE_HERO", components={"visual_anchor": {"kind": "icon", "icon_key": "rocket", "caption": "Main idea"}}),
                _v2_slide(
                    2,
                    "GRID_COMPOSITE",
                    components={
                        "cards": [_card("01"), _card("02"), _card("03")],
                        "visual_anchor": {"kind": "source_page", "source_index": 1, "page": 4, "caption": "Detailed diagram"},
                    },
                )
                | {"visual": {"kind": "source_page", "source_index": 1, "page": 4, "alt": "Detailed diagram"}},
                _v2_slide(3, "DUAL_PILLARS", components={"cards": [_card("01"), _card("02")]}),
                _v2_slide(
                    4,
                    "METRIC_DASHBOARD",
                    components={
                        "metrics": [
                            {"icon_key": "cpu", "value": "CPU", "label": "Script budget", "context": "Profile hot paths"},
                            {"icon_key": "gauge", "value": "FPS", "label": "Frame target", "context": "Avoid spikes"},
                            {"icon_key": "database", "value": "RAM", "label": "Memory load", "context": "Use pooling"},
                        ]
                    },
                ),
                _v2_slide(5, "CHECKLIST", title="Preflight Checklist", components={"checklist": [{"icon_key": "check", "text": "Run final checks"}] * 4}),
            ],
        }

        repaired = _repair_deck_payload(payload)
        deck = SlideDeckPayload.model_validate(repaired)

        self.assertEqual(deck.slides[1].visual.kind, "none")
        self.assertEqual(deck.slides[1].components.visual_anchor.kind, "none")

    def test_materialize_visuals_skips_non_visual_layout_images(self) -> None:
        deck = {
            "title": "Deck",
            "slides": [
                {
                    "slide_number": 1,
                    "layout_type": "GRID_COMPOSITE",
                    "title": "Grid",
                    "components": {"visual_anchor": {"kind": "generated_image", "prompt": "expensive"}},
                    "visual": {"kind": "generated_image", "prompt": "expensive"},
                }
            ],
        }

        with patch("app.modules.slides.tasks._generate_image_data_url") as generate_image:
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

        generate_image.assert_not_called()
        self.assertEqual(result["slides"][0]["visual"]["kind"], "none")
        self.assertEqual(result["slides"][0]["components"]["visual_anchor"]["kind"], "none")

    def test_render_deck_pdf_for_config_uses_browser_renderer(self) -> None:
        config = SimpleNamespace(
            pdf_renderer="browser",
            pdf_renderer_fallback="pillow",
            browser_render_timeout_seconds=12,
            browser_max_retries=1,
            browser_screenshot_scale=2,
        )
        deck = {"slides": [{"slide_number": 1, "title": "One"}]}

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.modules.slides.tasks.render_deck_pdf_with_browser"
        ) as browser_renderer:
            pdf_path = Path(temp_dir) / "deck.pdf"
            result = _render_deck_pdf_for_config(deck, pdf_path, config)

        self.assertEqual(result, "browser")
        browser_renderer.assert_called_once()
        self.assertEqual(browser_renderer.call_args.kwargs["timeout_seconds"], 12)

    def test_render_deck_pdf_for_config_retries_and_falls_back_to_pillow(self) -> None:
        config = SimpleNamespace(
            pdf_renderer="browser",
            pdf_renderer_fallback="pillow",
            browser_render_timeout_seconds=5,
            browser_max_retries=2,
            browser_screenshot_scale=2,
        )
        deck = {"slides": [{"slide_number": 1, "title": "One"}]}

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.modules.slides.tasks.render_deck_pdf_with_browser",
            side_effect=RuntimeError("chromium unavailable"),
        ) as browser_renderer, patch("app.modules.slides.tasks._render_deck_pdf") as pillow_renderer:
            pdf_path = Path(temp_dir) / "deck.pdf"
            result = _render_deck_pdf_for_config(deck, pdf_path, config)

        self.assertEqual(result, "pillow_fallback")
        self.assertEqual(browser_renderer.call_count, 3)
        pillow_renderer.assert_called_once_with(deck, pdf_path)

    def test_render_deck_pdf_for_config_raises_when_fallback_disabled(self) -> None:
        config = SimpleNamespace(
            pdf_renderer="browser",
            pdf_renderer_fallback="none",
            browser_render_timeout_seconds=5,
            browser_max_retries=0,
            browser_screenshot_scale=2,
        )
        deck = {"slides": [{"slide_number": 1, "title": "One"}]}

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.modules.slides.tasks.render_deck_pdf_with_browser",
            side_effect=RuntimeError("chromium unavailable"),
        ), self.assertRaises(RuntimeError):
            _render_deck_pdf_for_config(deck, Path(temp_dir) / "deck.pdf", config)

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
