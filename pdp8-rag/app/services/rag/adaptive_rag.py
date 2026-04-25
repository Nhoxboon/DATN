"""Adaptive RAG that chooses between single-hop and multi-hop based on query complexity."""

import dspy
from typing import Literal
from app.services.rag.dspy_rag import RAGModule
from app.services.rag.multihop_rag import MultiHopRAG


class AssessQueryComplexity(dspy.Signature):
    """Assess whether a query requires multi-hop reasoning or single-hop retrieval."""

    question: str = dspy.InputField(desc="User's question")
    complexity: Literal["simple", "complex"] = dspy.OutputField(
        desc="'simple' for factual questions answerable from one section, "
             "'complex' for questions requiring information from multiple sections, "
             "comparisons, analysis, or multi-part answers"
    )
    reasoning: str = dspy.OutputField(desc="Brief explanation of the complexity assessment")


class AdaptiveRAG(dspy.Module):
    """RAG that adaptively chooses between single-hop and multi-hop retrieval."""

    def __init__(
        self,
        retrieval_service,
        single_hop_passages: int = 10,
        max_hops: int = 4,
        passages_per_hop: int = 4
    ):
        """
        Initialize adaptive RAG.

        Args:
            retrieval_service: Retrieval service
            single_hop_passages: Number of passages for single-hop
            max_hops: Maximum hops for multi-hop
            passages_per_hop: Passages per hop for multi-hop
        """
        super().__init__()
        self.retrieval_service = retrieval_service

        # Initialize both RAG strategies
        self.single_hop = RAGModule(
            retrieval_service=retrieval_service,
            num_passages=single_hop_passages
        )
        self.multi_hop = MultiHopRAG(
            retrieval_service=retrieval_service,
            max_hops=max_hops,
            passages_per_hop=passages_per_hop
        )

        # Initialize complexity assessor
        self.assess_complexity = dspy.ChainOfThought(AssessQueryComplexity)
        self.doc_names: list[str] | None = None  # Will be set by RAGService if filtering needed

    def forward(self, question: str, doc_names=None):
        """
        Answer question using adaptive retrieval strategy.

        Args:
            question: User's question
            doc_names: Optional list of document names to filter

        Returns:
            Prediction with answer and metadata about strategy used
        """
        # Use instance doc_ids if not provided in forward call
        if doc_names is None:
            doc_names = self.doc_names

        # Set doc_names on sub-modules
        self.single_hop.doc_names = doc_names
        self.multi_hop.doc_names = doc_names

        # When filtering by specific documents, prefer single-hop (already focused scope)
        # Skip expensive complexity assessment
        if doc_names is not None and len(doc_names) <= 2:
            prediction = self.single_hop(question=question, doc_names=doc_names)
            prediction.strategy = "single-hop"
            prediction.strategy_reasoning = "Using single-hop for document-filtered query (focused scope)"
            return prediction

        # Assess query complexity for unfiltered or multi-document queries
        assessment = self.assess_complexity(question=question)

        # Choose strategy based on complexity
        if assessment.complexity == "complex":
            prediction = self.multi_hop(question=question, doc_names=doc_names)
            prediction.strategy = "multi-hop"
            prediction.strategy_reasoning = assessment.reasoning
        else:
            prediction = self.single_hop(question=question, doc_names=doc_names)
            prediction.strategy = "single-hop"
            prediction.strategy_reasoning = assessment.reasoning

        return prediction
