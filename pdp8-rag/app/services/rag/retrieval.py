"""Retrieval service for RAG with multi-document search and reranking."""

from typing import List, Dict, Any, Optional
from supabase import Client
from app.services.embedding import EmbeddingService
from app.services.reranker import RerankerService
from app.db.repository import get_document_repository
from app.core.config import get_app_config


class RetrievalService:
    """Service for retrieving relevant document chunks with optional reranking."""

    def __init__(
        self,
        supabase_client: Client,
        embedding_service: EmbeddingService,
        top_k: int = 5,
        use_reranking: bool = True
    ):
        """
        Initialize retrieval service.

        Args:
            supabase_client: Supabase client instance
            embedding_service: Embedding service for query embedding
            top_k: Number of top results to retrieve
            use_reranking: Whether to use cross-encoder reranking
        """
        self.supabase_client = supabase_client
        self.embedding_service = embedding_service
        self.top_k = top_k
        self.use_reranking = use_reranking
        self.doc_repo = get_document_repository(supabase_client)

        # Initialize reranker if enabled
        self.reranker = None
        if use_reranking:
            try:
                app_config = get_app_config()
                reranker_model = app_config.rag.reranking.model
                # Use CPU for reranking to avoid MPS memory issues on Mac
                self.reranker = RerankerService(model_name=reranker_model, force_cpu=True)
            except Exception as e:
                print(f"Warning: Could not initialize reranker: {e}")
                self.use_reranking = False

    def retrieve(
        self,
        query: str,
        document_name: Optional[str] = None,
        doc_names: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant chunks for a query.

        When document_name and doc_ids are None, retrieves from ALL documents using multi-document search:
        1. Get top-k chunks from EACH document
        2. Rerank all results using cross-encoder
        3. Return overall top-k chunks

        This ensures diversity across documents while maintaining relevance.

        Args:
            query: User query
            document_name: Optional document name to filter results (None = all documents)
            doc_names: Optional list of document names to filter results (takes precedence over document_name)

        Returns:
            List of retrieved chunks with metadata
        """
        # Generate query embedding once
        query_embedding = self.embedding_service.embed_text(query)

        # If doc_names or document_name specified, do filtered search
        if doc_names is not None or document_name is not None:
            # Skip reranking for single document (already focused)
            # Only rerank when searching multiple documents
            should_rerank = (
                self.use_reranking and
                self.reranker and
                doc_names is not None and
                len(doc_names) > 1
            )

            # Get more results if we're going to rerank
            limit = self.top_k * 2 if should_rerank else self.top_k

            results = self.doc_repo.search_similar(
                query_embedding=query_embedding,
                limit=limit,
                document_name=document_name,
                doc_names=doc_names
            )

            # Rerank only for multi-document queries
            if should_rerank and results:
                results = self.reranker.rerank(query, results, top_k=self.top_k)
            else:
                results = results[:self.top_k]

            return results
        else:
            # Multi-document search with reranking
            return self._retrieve_multi_document(query, query_embedding)

    def _retrieve_multi_document(
        self,
        query: str,
        query_embedding: List[float]
    ) -> List[Dict[str, Any]]:
        """
        Retrieve from all documents using two-stage approach:

        Stage 1: Quick document ranking
        - Get top 1-2 chunks from EACH document (sparse scan)
        - Score documents by their best chunk similarity
        - Select top N most relevant documents

        Stage 2: Deep retrieval
        - Get more chunks from top N documents only
        - Rerank all results using cross-encoder
        - Return overall top_k chunks

        This reduces computation from (33 docs × 10 chunks = 330) to (~70-100 chunks total)

        Args:
            query: User query
            query_embedding: Pre-computed query embedding

        Returns:
            Reranked list of top-k chunks across all documents
        """
        app_config = get_app_config()

        # Stage 1 parameters: Quick scan
        initial_chunks_per_doc = getattr(app_config.rag.retrieval, "initial_chunks_per_doc", 2)
        top_n_documents = getattr(app_config.rag.retrieval, "top_n_documents", 5)

        # Stage 2 parameters: Deep search
        deep_chunks_per_doc = getattr(app_config.rag.retrieval, "deep_chunks_per_doc", 8)

        # Get list of all documents
        all_documents = self.doc_repo.list_documents()
        print(f"[DEBUG] Stage 1: Quick scan of {len(all_documents)} documents")

        if not all_documents:
            return []

        # Stage 1: Quick scan - get top 1-2 chunks from each document
        document_scores = {}
        initial_results = []

        for doc_name in all_documents:
            doc_results = self.doc_repo.search_similar(
                query_embedding=query_embedding,
                limit=initial_chunks_per_doc,
                document_name=doc_name
            )

            if doc_results:
                # Score document by its best chunk's similarity
                best_similarity = max(chunk.get("similarity", 0.0) for chunk in doc_results)
                document_scores[doc_name] = best_similarity
                initial_results.extend(doc_results)

        print(f"[DEBUG] Stage 1: Got {len(initial_results)} chunks from initial scan")

        # Rank documents by their best similarity scores
        ranked_documents = sorted(
            document_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n_documents]

        top_doc_names = [doc_name for doc_name, score in ranked_documents]
        print(f"[DEBUG] Stage 1: Top {len(top_doc_names)} documents selected: {top_doc_names}")
        print(f"[DEBUG] Stage 1: Document scores: {[(doc, f'{score:.3f}') for doc, score in ranked_documents]}")

        # Stage 2: Deep retrieval from top documents only
        print(f"[DEBUG] Stage 2: Deep search in top {len(top_doc_names)} documents")
        deep_results = []

        for doc_name in top_doc_names:
            doc_results = self.doc_repo.search_similar(
                query_embedding=query_embedding,
                limit=deep_chunks_per_doc,
                document_name=doc_name
            )
            print(f"[DEBUG] Stage 2: Got {len(doc_results)} chunks from '{doc_name}'")
            deep_results.extend(doc_results)

        print(f"[DEBUG] Stage 2: Total {len(deep_results)} chunks before reranking")

        if not deep_results:
            return []

        # Stage 3: Rerank combined results if enabled
        if self.use_reranking and self.reranker:
            print(f"[DEBUG] Stage 3: Reranking {len(deep_results)} results to top {self.top_k}")
            final_results = self.reranker.rerank(query, deep_results, top_k=self.top_k)
        else:
            # Fallback: sort by embedding similarity
            final_results = sorted(
                deep_results,
                key=lambda x: x.get("similarity", 0.0),
                reverse=True
            )[:self.top_k]

        print(f"[DEBUG] Stage 3: Final results count: {len(final_results)}")
        return final_results

    def format_context(self, chunks: List[Dict[str, Any]]) -> str:
        """
        Format retrieved chunks into context string.

        Args:
            chunks: Retrieved chunks

        Returns:
            Formatted context string
        """
        context_parts = []

        for i, chunk in enumerate(chunks, 1):
            content = chunk.get("content", "")
            page_range = chunk.get("page_range", "unknown")
            document_name = chunk.get("document_name", "unknown")

            context_parts.append(
                f"[Source {i}] Document: {document_name}, Pages: {page_range}\n{content}"
            )

        return "\n\n---\n\n".join(context_parts)
