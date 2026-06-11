"""Benchmark-style tests for Naive RAG vs two-stage retrieval."""

from __future__ import annotations

import csv
import io
import json
import unittest
from contextlib import redirect_stdout
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from app.services.rag.retrieval import RetrievalService


ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "rag_two_stage_benchmark"

DOC_COUNT = 33
NAIVE_CHUNKS_PER_DOC = 10
INITIAL_CHUNKS_PER_DOC = 2
TOP_N_DOCUMENTS = 5
DEEP_CHUNKS_PER_DOC = 8
TOP_K = 10

EXPECTED_SOURCE_IDS = {
    "doc-01#1",
    "doc-02#1",
    "doc-03#1",
    "doc-04#1",
    "doc-05#1",
}


class RAGTwoStageBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_two_stage_benchmark()
        write_benchmark_artifacts(cls.result, ARTIFACT_DIR)

    def test_two_stage_uses_expected_candidate_budget(self) -> None:
        summary = {row["strategy"]: row for row in self.result["summary"]}

        self.assertEqual(summary["naive"]["rerank_candidates"], 330)
        self.assertEqual(summary["two_stage"]["stage1_scan_chunks"], 66)
        self.assertEqual(summary["two_stage"]["selected_documents"], 5)
        self.assertEqual(summary["two_stage"]["rerank_candidates"], 40)

    def test_two_stage_reduces_cross_encoder_workload_by_88_percent(self) -> None:
        summary = {row["strategy"]: row for row in self.result["summary"]}

        self.assertAlmostEqual(summary["two_stage"]["rerank_reduction"], 0.878788, places=6)
        self.assertGreater(summary["two_stage"]["estimated_speedup"], 7.0)

    def test_two_stage_preserves_oracle_source_recall(self) -> None:
        summary = {row["strategy"]: row for row in self.result["summary"]}

        self.assertEqual(summary["naive"]["oracle_source_recall"], 1.0)
        self.assertEqual(summary["two_stage"]["oracle_source_recall"], 1.0)

    def test_report_outputs_csv_json_and_svg_chart(self) -> None:
        self.assertTrue((ARTIFACT_DIR / "summary.csv").exists())
        self.assertTrue((ARTIFACT_DIR / "details.json").exists())
        chart = (ARTIFACT_DIR / "strategy_comparison.svg").read_text(encoding="utf-8")
        self.assertIn("Naive RAG", chart)
        self.assertIn("Two-stage + Reranking", chart)
        self.assertIn("87.88% less Cross-Encoder work", chart)
        self.assertIn("synthetic benchmark", chart)


def run_two_stage_benchmark() -> dict[str, Any]:
    naive_repo = FakeDocumentRepository()
    naive_reranker = FakeReranker()
    naive_sources = run_naive_rag(naive_repo, naive_reranker)
    naive_row = strategy_row(
        strategy="naive",
        display_name="Naive RAG",
        stage1_scan_chunks=0,
        selected_documents=DOC_COUNT,
        rerank_candidates=naive_reranker.candidate_counts[0],
        sources=naive_sources,
        search_calls=naive_repo.search_calls,
    )

    two_stage_repo = FakeDocumentRepository()
    two_stage_reranker = FakeReranker()
    service = object.__new__(RetrievalService)
    service.doc_repo = two_stage_repo
    service.top_k = TOP_K
    service.use_reranking = True
    service.reranker = two_stage_reranker
    service._notebook_id = ContextVar("test_rag_two_stage_notebook_id", default=None)
    service._get_reranker = lambda: two_stage_reranker

    token = service.set_notebook_scope("notebook-benchmark")
    try:
        # RetrievalService currently prints debug lines; keep benchmark test output clean.
        with redirect_stdout(io.StringIO()):
            two_stage_sources = service._retrieve_multi_document("How does RAG retrieve evidence?", [0.1, 0.2])
    finally:
        service.reset_notebook_scope(token)

    two_stage_row = strategy_row(
        strategy="two_stage",
        display_name="Two-stage + Reranking",
        stage1_scan_chunks=sum(call["returned"] for call in two_stage_repo.search_calls if call["limit"] == 2),
        selected_documents=len({call["document_name"] for call in two_stage_repo.search_calls if call["limit"] == 8}),
        rerank_candidates=two_stage_reranker.candidate_counts[0],
        sources=two_stage_sources,
        search_calls=two_stage_repo.search_calls,
    )
    two_stage_row["rerank_reduction"] = round(
        1 - two_stage_row["rerank_candidates"] / naive_row["rerank_candidates"],
        6,
    )
    two_stage_row["estimated_speedup"] = round(
        naive_row["estimated_latency_ms"] / two_stage_row["estimated_latency_ms"],
        6,
    )
    naive_row["rerank_reduction"] = 0.0
    naive_row["estimated_speedup"] = 1.0

    return {
        "summary": [naive_row, two_stage_row],
        "details": {
            "benchmark_type": "synthetic oracle retrieval workload benchmark",
            "accuracy_note": (
                "This benchmark does not measure real DSPy/LLM answer accuracy. "
                "It measures whether both retrieval strategies keep the labeled source chunks."
            ),
            "doc_count": DOC_COUNT,
            "naive_formula": f"{DOC_COUNT} documents * {NAIVE_CHUNKS_PER_DOC} chunks/document",
            "two_stage_formula": (
                f"stage1={DOC_COUNT}*{INITIAL_CHUNKS_PER_DOC}; "
                f"stage2={TOP_N_DOCUMENTS}*{DEEP_CHUNKS_PER_DOC}"
            ),
            "expected_sources": sorted(EXPECTED_SOURCE_IDS),
            "naive_search_calls": naive_repo.search_calls,
            "two_stage_search_calls": two_stage_repo.search_calls,
        },
    }


def run_naive_rag(repo: "FakeDocumentRepository", reranker: "FakeReranker") -> list[dict[str, Any]]:
    chunks = []
    for document_name in repo.list_documents("notebook-benchmark"):
        chunks.extend(
            repo.search_similar(
                query_embedding=[0.1, 0.2],
                notebook_id="notebook-benchmark",
                limit=NAIVE_CHUNKS_PER_DOC,
                document_name=document_name,
            )
        )
    return reranker.rerank("How does RAG retrieve evidence?", chunks, top_k=TOP_K)


def strategy_row(
    *,
    strategy: str,
    display_name: str,
    stage1_scan_chunks: int,
    selected_documents: int,
    rerank_candidates: int,
    sources: list[dict[str, Any]],
    search_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    source_ids = {source_id(source) for source in sources}
    oracle_source_recall = len(source_ids & EXPECTED_SOURCE_IDS) / len(EXPECTED_SOURCE_IDS)
    estimated_latency_ms = estimate_latency_ms(stage1_scan_chunks, rerank_candidates)
    return {
        "strategy": strategy,
        "display_name": display_name,
        "stage1_scan_chunks": stage1_scan_chunks,
        "selected_documents": selected_documents,
        "search_calls": len(search_calls),
        "rerank_candidates": rerank_candidates,
        "oracle_source_recall": round(oracle_source_recall, 6),
        "estimated_latency_ms": round(estimated_latency_ms, 3),
    }


def estimate_latency_ms(stage1_scan_chunks: int, rerank_candidates: int) -> float:
    # HNSW/Bi-Encoder scan is cheap; Cross-Encoder pair scoring dominates runtime.
    return 20.0 + stage1_scan_chunks * 0.05 + rerank_candidates * 4.0


def source_id(source: dict[str, Any]) -> str:
    return f"{source['document_name']}#{source['chunk_id']}"


class FakeDocumentRepository:
    def __init__(self) -> None:
        self.documents = [f"doc-{index:02d}" for index in range(1, DOC_COUNT + 1)]
        self.search_calls: list[dict[str, Any]] = []
        self.chunks_by_document = {
            document_name: self._chunks_for_document(document_name)
            for document_name in self.documents
        }

    def list_documents(self, notebook_id: str) -> list[str]:
        self.notebook_id = notebook_id
        return list(self.documents)

    def search_similar(
        self,
        query_embedding: list[float],
        notebook_id: str,
        limit: int = 5,
        document_name: str | None = None,
        doc_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if document_name is None:
            raise ValueError("Benchmark repository expects document-scoped searches.")
        results = self.chunks_by_document[document_name][:limit]
        self.search_calls.append(
            {
                "document_name": document_name,
                "doc_names": doc_names,
                "limit": limit,
                "returned": len(results),
                "notebook_id": notebook_id,
                "query_embedding": query_embedding,
            }
        )
        return [dict(result) for result in results]

    def _chunks_for_document(self, document_name: str) -> list[dict[str, Any]]:
        doc_number = int(document_name.split("-")[1])
        is_relevant_doc = doc_number <= TOP_N_DOCUMENTS
        document_priority = (DOC_COUNT - doc_number) / 1000
        chunks = []
        for chunk_id in range(1, NAIVE_CHUNKS_PER_DOC + 1):
            if is_relevant_doc and chunk_id == 1:
                similarity = 0.95 - doc_number * 0.01
                rerank_score = 1.0 - doc_number * 0.01
                content = f"Gold evidence from {document_name} for two-stage RAG."
            elif is_relevant_doc:
                similarity = 0.82 - doc_number * 0.01 - chunk_id * 0.002
                rerank_score = 0.60 - chunk_id * 0.01
                content = f"Supporting context {chunk_id} from {document_name}."
            else:
                similarity = 0.50 + document_priority - chunk_id * 0.002
                rerank_score = 0.10 - chunk_id * 0.001
                content = f"Background context {chunk_id} from {document_name}."
            chunks.append(
                {
                    "document_name": document_name,
                    "chunk_id": chunk_id,
                    "content": content,
                    "similarity": round(similarity, 6),
                    "rerank_score": round(rerank_score, 6),
                }
            )
        return sorted(chunks, key=lambda chunk: chunk["similarity"], reverse=True)


class FakeReranker:
    def __init__(self) -> None:
        self.candidate_counts: list[int] = []

    def rerank(self, query: str, chunks: list[dict[str, Any]], top_k: int = TOP_K) -> list[dict[str, Any]]:
        self.query = query
        self.candidate_counts.append(len(chunks))
        return sorted(chunks, key=lambda chunk: chunk["rerank_score"], reverse=True)[:top_k]


def write_benchmark_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "details.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_summary_csv(result["summary"], output_dir / "summary.csv")
    (output_dir / "strategy_comparison.svg").write_text(
        render_strategy_chart(result["summary"]),
        encoding="utf-8",
    )


def write_summary_csv(summary: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)


def render_strategy_chart(summary: list[dict[str, Any]]) -> str:
    naive = next(row for row in summary if row["strategy"] == "naive")
    two_stage = next(row for row in summary if row["strategy"] == "two_stage")
    width = 900
    height = 470
    left = 80
    right = 40
    top = 60
    baseline = 300
    max_candidates = max(row["rerank_candidates"] for row in summary)
    colors = {"naive": "#dc2626", "two_stage": "#16a34a"}

    def bar_height(candidates: int) -> float:
        return 220 * candidates / max_candidates

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="70" y="32" font-family="Arial" font-size="19" font-weight="700">Naive RAG vs Two-stage + Reranking</text>',
        f'<line x1="{left}" y1="{baseline}" x2="{width - right}" y2="{baseline}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseline}" stroke="#111827"/>',
    ]

    for index, row in enumerate(summary):
        x = 190 + index * 290
        h = bar_height(row["rerank_candidates"])
        y = baseline - h
        color = colors[row["strategy"]]
        parts.append(
            f'<rect x="{x}" y="{y:.1f}" width="150" height="{h:.1f}" fill="{color}">'
            f'<title>{row["display_name"]}: {row["rerank_candidates"]} rerank candidates</title></rect>'
        )
        parts.append(f'<text x="{x + 75}" y="{baseline + 24}" text-anchor="middle" font-family="Arial" font-size="13">{row["display_name"]}</text>')
        parts.append(f'<text x="{x + 75}" y="{y - 10:.1f}" text-anchor="middle" font-family="Arial" font-size="16" font-weight="700">{row["rerank_candidates"]}</text>')
        parts.append(f'<text x="{x + 75}" y="{baseline + 44}" text-anchor="middle" font-family="Arial" font-size="12">Oracle source recall: {row["oracle_source_recall"] * 100:.0f}%</text>')
        parts.append(f'<text x="{x + 75}" y="{baseline + 62}" text-anchor="middle" font-family="Arial" font-size="12">Latency est.: {row["estimated_latency_ms"]:.1f} ms</text>')

    reduction_percent = two_stage["rerank_reduction"] * 100
    parts.extend(
        [
            f'<text x="70" y="390" font-family="Arial" font-size="14">Naive workload: {DOC_COUNT} docs x {NAIVE_CHUNKS_PER_DOC} chunks = {naive["rerank_candidates"]} Cross-Encoder pairs</text>',
            f'<text x="70" y="414" font-family="Arial" font-size="14">Two-stage workload: {TOP_N_DOCUMENTS} docs x {DEEP_CHUNKS_PER_DOC} chunks = {two_stage["rerank_candidates"]} Cross-Encoder pairs</text>',
            f'<text x="70" y="438" font-family="Arial" font-size="15" font-weight="700">{reduction_percent:.2f}% less Cross-Encoder work; oracle source recall remains 100% in this synthetic benchmark</text>',
        ]
    )
    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
