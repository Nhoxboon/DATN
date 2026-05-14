"""Tests for cached RAG streaming path."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.rag.service import RAGService


class FakeRetrievalService:
    def __init__(self) -> None:
        self.reset_tokens: list[str] = []

    def set_notebook_scope(self, notebook_id: str) -> str:
        self.notebook_id = notebook_id
        return "scope-token"

    def reset_notebook_scope(self, token: str) -> None:
        self.reset_tokens.append(token)


class FakeCacheService:
    def get_cache_name(self, _cache_key: str) -> str:
        return "cachedContents/test"

    def get_cache_manifest(self, _manifest_key: str) -> list[dict[str, object]]:
        return [
            {"document": "doc-a", "page_range": "1"},
            {"document": "doc-b", "page_range": "2"},
        ]

    def generate_with_cache(self, **_kwargs: object) -> str:
        return "Cached answer [2]."


class RAGStreamCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_stream_uses_global_re_and_yields_metadata(self) -> None:
        service = object.__new__(RAGService)
        service.retrieval_service = FakeRetrievalService()
        service.cache_service = FakeCacheService()
        service.app_config = SimpleNamespace(
            llm=SimpleNamespace(gemini=SimpleNamespace(temperature=0.0, max_tokens=256))
        )

        events = [
            event
            async for event in service.query_stream(
                "What changed?",
                "notebook-1",
                doc_names=["doc-a"],
            )
        ]

        tokens = [event["content"] for event in events if event["type"] == "token"]
        metadata = [event for event in events if event["type"] == "metadata"]

        self.assertEqual("".join(tokens), "Cached answer [1].")
        self.assertEqual(metadata[0]["strategy"], "cached-single-hop")
        self.assertEqual(metadata[0]["sources"], [{"document": "doc-b", "page_range": "2"}])
        self.assertEqual(service.retrieval_service.reset_tokens, ["scope-token"])


if __name__ == "__main__":
    unittest.main()
