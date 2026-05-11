"""Reranking service for improving retrieval quality using state-of-the-art models."""

from typing import List, Dict, Any
import torch
from sentence_transformers import CrossEncoder


class RerankerService:
    """Service for reranking retrieved documents using state-of-the-art cross-encoder models."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", force_cpu: bool = False):
        """
        Initialize reranker service.

        Recommended models (as of 2024-2025):
        - Speed: "cross-encoder/ms-marco-MiniLM-L-6-v2" (legacy, 2021)
        - Balanced: "mixedbread-ai/mxbai-rerank-large-v1" (production-ready)
        - Accuracy (SOTA): "BAAI/bge-reranker-v2-m3" (best open-source)
        - Enterprise API: Use Cohere Rerank or Google Vertex AI Ranking API

        Args:
            model_name: Name of the cross-encoder model to use
            force_cpu: Force CPU mode (useful if GPU has memory issues)
        """
        # Detect device (CUDA for NVIDIA, MPS for Mac M-chips, or CPU)
        if force_cpu:
            device = "cpu"
        else:
            device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

        print(f"Loading Reranker model {model_name} on {device}...")
        self.model = CrossEncoder(model_name, device=device)
        self.device = device

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: int = 10,
        batch_size: int = 2,
        max_content_length: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Rerank retrieved chunks using cross-encoder model.

        This provides much more accurate relevance scoring than embedding similarity alone.
        The cross-encoder sees both query and document together, enabling nuanced understanding.

        Args:
            query: User query
            chunks: List of retrieved chunks with metadata
            top_k: Number of top results to return after reranking
            batch_size: Number of chunks to process at once (to avoid OOM)
            max_content_length: Maximum characters of content to use for reranking

        Returns:
            Reranked list of chunks with updated similarity scores
        """
        if not chunks:
            return []

        # Prepare query-document pairs for cross-encoder
        # Truncate content to avoid OOM - rerankers work well with first N characters
        # BGE models support up to 8192 tokens, but we truncate to save memory
        pairs = [
            (query, chunk.get("content", "")[:max_content_length])
            for chunk in chunks
        ]

        # Process in batches to avoid GPU memory issues
        all_scores = []
        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i:i + batch_size]

            try:
                # Get cross-encoder scores for this batch
                # convert_to_tensor=True enables GPU acceleration for batch processing
                batch_scores = self.model.predict(batch_pairs, convert_to_tensor=True)

                # Convert tensor to list of floats
                if isinstance(batch_scores, torch.Tensor):
                    batch_scores = batch_scores.tolist()

                all_scores.extend(batch_scores)

                # Clear GPU cache after each batch
                if self.device in ["cuda", "mps"]:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    elif torch.backends.mps.is_available():
                        torch.mps.empty_cache()

            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    print(f"⚠️  GPU OOM on batch {i//batch_size + 1}, falling back to CPU...")
                    # Fall back to CPU for this batch
                    self.model.device = "cpu"
                    self.model.model.to("cpu")
                    batch_scores = self.model.predict(batch_pairs, convert_to_tensor=False)
                    all_scores.extend(batch_scores)
                else:
                    raise

        # Add cross-encoder scores to chunks
        for chunk, score in zip(chunks, all_scores):
            chunk["rerank_score"] = float(score)
            # Keep original embedding similarity for reference/debugging
            if "similarity" not in chunk:
                chunk["similarity"] = 0.0

        # Sort by rerank score (descending)
        # Use -inf as default to handle any chunks without scores
        reranked_chunks = sorted(
            chunks,
            key=lambda x: x.get("rerank_score", -float('inf')),
            reverse=True
        )

        # Return top-k results
        return reranked_chunks[:top_k]
