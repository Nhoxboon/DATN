"""Benchmark-style tests for comparing RAG similarity thresholds."""

from __future__ import annotations

import csv
import json
import re
import unittest
from collections import Counter
from pathlib import Path
from typing import Any


THRESHOLDS = [0.4, 0.6, 0.7, 0.8]
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "rag_threshold_benchmark"

WORD_RE = re.compile(r"\b[\w]+(?:[-'][\w]+)?\b", re.UNICODE)
CITATION_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "the",
    "this",
    "when",
    "with",
}

BENCHMARK_CASES = [
    {
        "id": "registration",
        "question": "How does registration work?",
        "reference_answer": (
            "Registration uses Supabase Auth for email and password accounts. "
            "The backend validates duplicate emails before creating a user."
        ),
        "required_facts": ["Supabase Auth", "email and password", "duplicate emails"],
        "expected_sources": ["auth#1", "auth#2"],
        "candidates": [
            {
                "source_id": "auth#1",
                "similarity": 0.86,
                "fact": "Registration uses Supabase Auth for email and password accounts",
            },
            {
                "source_id": "auth#2",
                "similarity": 0.72,
                "fact": "The backend validates duplicate emails before creating a user",
            },
            {
                "source_id": "slides#4",
                "similarity": 0.48,
                "fact": "Slide decks are rendered to PDF by the browser renderer",
            },
        ],
    },
    {
        "id": "pdf_pages",
        "question": "How are PDF chunk pages preserved?",
        "reference_answer": (
            "PDF chunks preserve marker page boundaries. "
            "When markers are missing, pages are distributed across the text."
        ),
        "required_facts": ["marker page boundaries", "pages are distributed"],
        "expected_sources": ["pdf#1", "pdf#2"],
        "candidates": [
            {
                "source_id": "pdf#1",
                "similarity": 0.78,
                "fact": "PDF chunks preserve marker page boundaries",
            },
            {
                "source_id": "pdf#2",
                "similarity": 0.64,
                "fact": "When markers are missing, pages are distributed across the text",
            },
            {
                "source_id": "audio#3",
                "similarity": 0.43,
                "fact": "Audio overviews use Gemini text to speech",
            },
        ],
    },
    {
        "id": "cached_citations",
        "question": "How are cached RAG citations made safe?",
        "reference_answer": (
            "Cached RAG answers must resolve citations against the source manifest. "
            "The service refreshes similarity scores for cited chunks."
        ),
        "required_facts": ["source manifest", "similarity scores"],
        "expected_sources": ["cache#1", "cache#2"],
        "candidates": [
            {
                "source_id": "cache#1",
                "similarity": 0.80,
                "fact": "Cached RAG answers must resolve citations against the source manifest",
            },
            {
                "source_id": "cache#2",
                "similarity": 0.61,
                "fact": "The service refreshes similarity scores for cited chunks",
            },
            {
                "source_id": "notes#6",
                "similarity": 0.44,
                "fact": "Notebook notes save an answer in Studio",
            },
        ],
    },
]


class RAGThresholdBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_threshold_benchmark()
        write_benchmark_artifacts(cls.result, ARTIFACT_DIR)

    def test_threshold_sweep_finds_best_accuracy_recall_tradeoff(self) -> None:
        best = max(self.result["summary"], key=lambda row: row["quality_score"])

        self.assertEqual(best["threshold"], 0.6)
        self.assertGreater(best["answer_accuracy"], 0.90)
        self.assertEqual(best["retrieval_recall"], 1.0)

    def test_low_threshold_adds_noise_to_answers(self) -> None:
        by_threshold = {row["threshold"]: row for row in self.result["summary"]}

        self.assertGreater(by_threshold[0.4]["source_count"], by_threshold[0.6]["source_count"])
        self.assertLess(by_threshold[0.4]["answer_accuracy"], by_threshold[0.6]["answer_accuracy"])

    def test_high_threshold_loses_relevant_context(self) -> None:
        by_threshold = {row["threshold"]: row for row in self.result["summary"]}

        self.assertLess(by_threshold[0.8]["retrieval_recall"], by_threshold[0.6]["retrieval_recall"])
        self.assertLess(by_threshold[0.8]["faithfulness"], by_threshold[0.6]["faithfulness"])

    def test_report_outputs_csv_json_and_svg_chart(self) -> None:
        self.assertTrue((ARTIFACT_DIR / "summary.csv").exists())
        self.assertTrue((ARTIFACT_DIR / "details.json").exists())
        self.assertTrue((ARTIFACT_DIR / "threshold_comparison.svg").exists())
        self.assertIn(
            "RAG threshold comparison",
            (ARTIFACT_DIR / "threshold_comparison.svg").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "faithfulness",
            (ARTIFACT_DIR / "threshold_comparison.svg").read_text(encoding="utf-8"),
        )


def run_threshold_benchmark() -> dict[str, Any]:
    rows = []
    for threshold in THRESHOLDS:
        for case in BENCHMARK_CASES:
            prediction = generate_answer(case, threshold)
            rows.append(
                {
                    "threshold": threshold,
                    "case_id": case["id"],
                    **score_prediction(case, prediction),
                    "answer": prediction["answer"],
                }
            )

    summary = []
    for threshold in THRESHOLDS:
        threshold_rows = [row for row in rows if row["threshold"] == threshold]
        item = {
            "threshold": threshold,
            "answer_accuracy": mean(row["answer_accuracy"] for row in threshold_rows),
            "faithfulness": mean(row["faithfulness"] for row in threshold_rows),
            "retrieval_recall": mean(row["retrieval_recall"] for row in threshold_rows),
            "citation_validity": mean(row["citation_validity"] for row in threshold_rows),
            "source_count": mean(row["source_count"] for row in threshold_rows),
        }
        item["quality_score"] = (
            0.45 * item["answer_accuracy"]
            + 0.35 * item["faithfulness"]
            + 0.20 * item["retrieval_recall"]
        )
        summary.append({key: round(value, 6) for key, value in item.items()})

    return {"summary": summary, "rows": rows}


def generate_answer(case: dict[str, Any], threshold: float) -> dict[str, Any]:
    sources = [
        candidate
        for candidate in sorted(case["candidates"], key=lambda item: item["similarity"], reverse=True)
        if candidate["similarity"] >= threshold
    ]
    if not sources:
        return {"answer": "Not enough evidence in the retrieved context.", "sources": []}

    answer = " ".join(
        f"{source['fact']} [{index}]."
        for index, source in enumerate(sources, start=1)
    )
    return {"answer": answer, "sources": sources}


def score_prediction(case: dict[str, Any], prediction: dict[str, Any]) -> dict[str, float]:
    answer = prediction["answer"]
    sources = prediction["sources"]
    source_text = " ".join(source["fact"] for source in sources)
    expected_sources = set(case["expected_sources"])
    retrieved_sources = {source["source_id"] for source in sources}
    fact_coverage = required_fact_coverage(answer, case["required_facts"])
    reference_f1 = token_f1(answer, case["reference_answer"])
    answer_accuracy = 0.65 * reference_f1 + 0.35 * fact_coverage
    source_support = source_token_support(answer, source_text)
    citation_validity = valid_citation_ratio(answer, len(sources))
    faithfulness = 0.65 * source_support + 0.35 * citation_validity

    return {
        "answer_accuracy": round(answer_accuracy, 6),
        "faithfulness": round(faithfulness, 6),
        "retrieval_recall": round(len(expected_sources & retrieved_sources) / len(expected_sources), 6),
        "citation_validity": round(citation_validity, 6),
        "source_count": float(len(sources)),
    }


def required_fact_coverage(answer: str, required_facts: list[str]) -> float:
    normalized_answer = " ".join(tokens(answer))
    hits = 0
    for fact in required_facts:
        normalized_fact = " ".join(tokens(fact))
        if normalized_fact in normalized_answer:
            hits += 1
    return hits / len(required_facts)


def token_f1(predicted: str, reference: str) -> float:
    predicted_tokens = Counter(content_tokens(predicted))
    reference_tokens = Counter(content_tokens(reference))
    overlap = sum((predicted_tokens & reference_tokens).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(predicted_tokens.values())
    recall = overlap / sum(reference_tokens.values())
    return 2 * precision * recall / (precision + recall)


def source_token_support(answer: str, source_text: str) -> float:
    answer_tokens = content_tokens(answer)
    source_tokens = set(content_tokens(source_text))
    if not answer_tokens or not source_tokens:
        return 0.0
    return sum(1 for token in answer_tokens if token in source_tokens) / len(answer_tokens)


def valid_citation_ratio(answer: str, source_count: int) -> float:
    citations = [
        int(value.strip())
        for match in CITATION_RE.finditer(answer)
        for value in match.group(1).split(",")
    ]
    if not citations or source_count == 0:
        return 0.0
    valid = sum(1 for citation in citations if 1 <= citation <= source_count)
    return valid / len(citations)


def tokens(text: str) -> list[str]:
    return [token.casefold() for token in WORD_RE.findall(text)]


def content_tokens(text: str) -> list[str]:
    return [token for token in tokens(text) if len(token) >= 3 and token not in STOPWORDS]


def mean(values: Any) -> float:
    values = list(values)
    return sum(values) / len(values)


def write_benchmark_artifacts(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "details.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_summary_csv(result["summary"], output_dir / "summary.csv")
    (output_dir / "threshold_comparison.svg").write_text(
        render_threshold_chart(result["summary"]),
        encoding="utf-8",
    )


def write_summary_csv(summary: list[dict[str, float]], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)


def render_threshold_chart(summary: list[dict[str, float]]) -> str:
    width = 960
    height = 520
    left = 72
    top = 48
    right = 32
    bottom = 120
    plot_width = width - left - right
    plot_height = height - top - bottom
    metrics = [
        ("answer_accuracy", "#2563eb"),
        ("faithfulness", "#16a34a"),
        ("retrieval_recall", "#d97706"),
        ("citation_validity", "#9333ea"),
    ]
    baseline = height - bottom
    group_width = plot_width / len(summary)
    bar_width = min(28.0, group_width / (len(metrics) + 1.4))
    group_padding = (group_width - bar_width * len(metrics)) / 2

    def y_at(value: float) -> float:
        return top + (1 - max(0.0, min(1.0, value))) * plot_height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="72" y="28" font-family="Arial" font-size="18" font-weight="700">RAG threshold comparison</text>',
    ]
    for tick in range(6):
        value = tick / 5
        y = y_at(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial" font-size="12">{value:.1f}</text>')

    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{baseline}" stroke="#111827"/>')
    parts.append(f'<line x1="{left}" y1="{baseline}" x2="{width - right}" y2="{baseline}" stroke="#111827"/>')

    for index, row in enumerate(summary):
        group_x = left + group_width * index
        label_x = group_x + group_width / 2
        parts.append(f'<text x="{label_x:.1f}" y="{baseline + 24}" text-anchor="middle" font-family="Arial" font-size="12">{row["threshold"]}</text>')
        for metric_index, (metric, color) in enumerate(metrics):
            value = row[metric]
            bar_x = group_x + group_padding + bar_width * metric_index
            bar_y = y_at(value)
            bar_height = baseline - bar_y
            parts.append(
                f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_width - 3:.1f}" '
                f'height="{bar_height:.1f}" fill="{color}">'
                f'<title>{metric} @ {row["threshold"]}: {value:.3f}</title></rect>'
            )

    legend_x = left
    legend_y = height - 58
    for metric, color in metrics:
        parts.append(f'<rect x="{legend_x}" y="{legend_y - 10}" width="12" height="12" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 18}" y="{legend_y}" font-family="Arial" font-size="12">{metric}</text>')
        legend_x += 205

    parts.append("</svg>")
    return "\n".join(parts)


if __name__ == "__main__":
    unittest.main()
