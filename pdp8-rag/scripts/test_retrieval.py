"""Test script to debug multi-document retrieval."""

import asyncio
from app.core.config import get_settings
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.services.rag.retrieval import RetrievalService
from app.db.repository import get_document_repository


async def test_retrieval():
    """Test multi-document retrieval."""
    # Initialize services
    settings = get_settings()
    supabase_client = get_supabase_client()
    embedding_service = EmbeddingService(settings)

    # Get document repository
    doc_repo = get_document_repository(supabase_client)

    # Check what documents exist
    print("=== Documents in Database ===")
    all_docs = doc_repo.list_documents()
    print(f"Found {len(all_docs)} documents:")
    for doc in all_docs:
        print(f"  - {doc}")
    print()

    # Test query
    query = "What are the renewable energy targets?"
    print(f"=== Testing Query: '{query}' ===\n")

    # Get query embedding
    query_embedding = embedding_service.embed_text(query)

    # Test retrieval from each document separately
    for doc_name in all_docs:
        print(f"--- Results from '{doc_name}' ---")
        results = doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=5,
            document_name=doc_name
        )
        print(f"Got {len(results)} results")
        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', 0)
            content_preview = result.get('content', '')[:100]
            print(f"  {i}. Similarity: {similarity:.4f}")
            print(f"     Preview: {content_preview}...")
        print()

    # Test multi-document retrieval
    print("=== Multi-Document Retrieval (No Filter) ===")
    all_results = doc_repo.search_similar(
        query_embedding=query_embedding,
        limit=10,
        document_name=None
    )
    print(f"Got {len(all_results)} results")
    for i, result in enumerate(all_results, 1):
        doc_name = result.get('document_name', 'unknown')
        similarity = result.get('similarity', 0)
        print(f"  {i}. Doc: {doc_name}, Similarity: {similarity:.4f}")
    print()

    # Test with RetrievalService (should use multi-doc + reranking)
    print("=== RetrievalService with Reranking ===")
    retrieval_service = RetrievalService(
        supabase_client=supabase_client,
        embedding_service=embedding_service,
        top_k=10,
        use_reranking=True
    )

    final_results = retrieval_service.retrieve(query, document_name=None)
    print(f"Got {len(final_results)} final results after reranking")
    for i, result in enumerate(final_results, 1):
        doc_name = result.get('document_name', 'unknown')
        rerank_score = result.get('rerank_score', None)
        similarity = result.get('similarity', 0)
        print(f"  {i}. Doc: {doc_name}")
        print(f"     Rerank Score: {rerank_score:.4f}" if rerank_score else f"     Similarity: {similarity:.4f}")
    print()


if __name__ == "__main__":
    asyncio.run(test_retrieval())
