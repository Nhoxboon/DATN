"""Tests for cached RAG streaming path."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.rag.service import RAGService


class FakeRetrievalService:
    def __init__(self, doc_repo: object | None = None) -> None:
        self.reset_tokens: list[str] = []
        self.embedding_service = FakeEmbeddingService()
        self.doc_repo = doc_repo or FakeDocRepo()

    def set_notebook_scope(self, notebook_id: str) -> str:
        self.notebook_id = notebook_id
        return "scope-token"

    def reset_notebook_scope(self, token: str) -> None:
        self.reset_tokens.append(token)


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeDocRepo:
    def __init__(
        self,
        results: dict[str, list[dict[str, object]]] | None = None,
        all_chunks: list[dict[str, object]] | None = None
    ) -> None:
        self.results = results or {
            "doc-a": [
                {"document_name": "doc-a", "chunk_id": 1, "similarity": 0.42},
                {"document_name": "doc-a", "chunk_id": 2, "similarity": 0.84},
            ]
        }
        self.search_calls: list[dict[str, object]] = []
        self.all_chunks = all_chunks or [
            {
                "document_name": "doc-a",
                "chunk_id": 1,
                "content": "Chunk one",
                "page_range": "1",
                "pages": [1],
                "metadata": {},
            },
            {
                "document_name": "doc-a",
                "chunk_id": 2,
                "content": "Chunk two",
                "page_range": "2",
                "pages": [2],
                "metadata": {},
            },
        ]
        self.get_all_calls: list[dict[str, object]] = []

    def search_similar(
        self,
        query_embedding: list[float],
        notebook_id: str,
        limit: int = 5,
        document_name: str | None = None,
        doc_names: list[str] | None = None
    ) -> list[dict[str, object]]:
        self.search_calls.append(
            {
                "query_embedding": query_embedding,
                "notebook_id": notebook_id,
                "limit": limit,
                "document_name": document_name,
                "doc_names": doc_names,
            }
        )
        return list(self.results.get(document_name or "", []))[:limit]

    def get_all_chunks_by_names(self, doc_names: list[str], notebook_id: str) -> list[dict[str, object]]:
        self.get_all_calls.append({"doc_names": doc_names, "notebook_id": notebook_id})
        return list(self.all_chunks)


class FakeCacheService:
    def get_cache_name(self, _cache_key: str) -> str:
        return "cachedContents/test"

    def get_cache_manifest(self, _manifest_key: str) -> list[dict[str, object]]:
        return [
            {"document": "doc-a", "chunk_id": 1, "page_range": "1"},
            {"document": "doc-a", "chunk_id": 2, "page_range": "2"},
        ]

    def generate_with_cache(self, **_kwargs: object) -> str:
        return "Cached answer [2]."

    def delete_cache(self, _cache_key: str) -> bool:
        return True

    def delete_cache_manifest(self, _manifest_key: str) -> bool:
        return True


class FakeRecreatingCacheService(FakeCacheService):
    def __init__(self) -> None:
        self.cache_name: str | None = "cachedContents/old"
        self.manifest: list[dict[str, object]] | None = [{"document": "doc-a", "page_range": "old"}]
        self.deleted_cache = False
        self.deleted_manifest = False
        self.created_source_manifest: list[dict[str, object]] | None = None

    def get_cache_name(self, _cache_key: str) -> str | None:
        return self.cache_name

    def get_cache_manifest(self, _manifest_key: str) -> list[dict[str, object]] | None:
        return self.manifest

    def delete_cache(self, _cache_key: str) -> bool:
        self.deleted_cache = True
        self.cache_name = None
        return True

    def delete_cache_manifest(self, _manifest_key: str) -> bool:
        self.deleted_manifest = True
        self.manifest = None
        return True

    def create_document_cache(
        self,
        _cache_key: str,
        _chunks: list[dict[str, object]],
        source_manifest: list[dict[str, object]],
        _manifest_key: str,
        ttl_hours: int = 1
    ) -> str:
        self.created_source_manifest = source_manifest
        self.manifest = source_manifest
        self.cache_name = "cachedContents/new"
        return self.cache_name


class RAGStreamCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_stream_scores_manifest_citations(self) -> None:
        doc_repo = FakeDocRepo()
        service = object.__new__(RAGService)
        service.retrieval_service = FakeRetrievalService(doc_repo)
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
        self.assertEqual(
            metadata[0]["sources"],
            [{"document": "doc-a", "chunk_id": 2, "page_range": "2", "similarity": 0.84}]
        )
        self.assertEqual(doc_repo.search_calls[0]["document_name"], "doc-a")
        self.assertEqual(doc_repo.search_calls[0]["limit"], 2)
        self.assertEqual(service.retrieval_service.reset_tokens, ["scope-token"])

    async def test_cached_stream_falls_back_when_similarity_cannot_be_resolved(self) -> None:
        doc_repo = FakeDocRepo(
            results={"doc-a": [{"document_name": "doc-a", "chunk_id": 99, "similarity": 0.1}]}
        )
        service = object.__new__(RAGService)
        service.retrieval_service = FakeRetrievalService(doc_repo)
        service.cache_service = FakeCacheService()
        service.app_config = SimpleNamespace(
            llm=SimpleNamespace(gemini=SimpleNamespace(temperature=0.0, max_tokens=256))
        )

        async def fake_query_stream_impl(
            _question: str,
            _notebook_id: str,
            _document_name: str | None = None,
            _doc_names: list[str] | None = None
        ):
            yield {"type": "token", "content": "Fallback answer"}
            yield {"type": "metadata", "strategy": "single-hop", "sources": []}

        service._query_stream_impl = fake_query_stream_impl

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

        self.assertEqual("".join(tokens), "Fallback answer")
        self.assertEqual(metadata[0]["strategy"], "single-hop")

    async def test_cached_stream_recreates_manifest_without_chunk_ids(self) -> None:
        doc_repo = FakeDocRepo()
        cache_service = FakeRecreatingCacheService()
        service = object.__new__(RAGService)
        service.retrieval_service = FakeRetrievalService(doc_repo)
        service.cache_service = cache_service
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

        metadata = [event for event in events if event["type"] == "metadata"]

        self.assertTrue(cache_service.deleted_cache)
        self.assertTrue(cache_service.deleted_manifest)
        self.assertIsNotNone(cache_service.created_source_manifest)
        assert cache_service.created_source_manifest is not None
        self.assertEqual(cache_service.created_source_manifest[0]["chunk_id"], 1)
        self.assertEqual(metadata[0]["sources"][0]["similarity"], 0.84)

    def test_format_source_keeps_chunk_id_without_fake_similarity(self) -> None:
        source = RAGService._format_source(
            {
                "document_name": "doc-a",
                "chunk_id": 7,
                "content": "Chunk text",
                "page_range": "3-4",
                "pages": [3, 4],
                "metadata": {},
            }
        )

        self.assertEqual(source["chunk_id"], 7)
        self.assertNotIn("similarity", source)


if __name__ == "__main__":
    unittest.main()
