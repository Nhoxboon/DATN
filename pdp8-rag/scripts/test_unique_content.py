"""Test retrieval with queries that should only match one document."""

import asyncio
from app.core.config import get_settings
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.services.rag.retrieval import RetrievalService


async def test_unique_content_query(query: str):
    """Test retrieval for content unique to one document."""
    settings = get_settings()
    supabase_client = get_supabase_client()
    embedding_service = EmbeddingService(settings)

    print("=" * 80)
    print(f"QUERY: {query}")
    print("=" * 80)

    # Get query embedding
    query_embedding = embedding_service.embed_text(query)

    # Test each document separately with embedding similarity
    print("\n[1] EMBEDDING SIMILARITY ONLY (Before Reranking)")
    print("-" * 80)

    doc1 = "pdp8"
    doc2 = "PDP8_full-with-annexes_EN"

    from app.db.repository import get_document_repository
    doc_repo = get_document_repository(supabase_client)

    for doc_name in [doc1, doc2]:
        results = doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=5,
            document_name=doc_name
        )

        print(f"\n{doc_name}:")
        if results:
            print(f"  Top similarity: {results[0].get('similarity', 0):.4f}")
            print(f"  Top 3 results:")
            for i, r in enumerate(results[:3], 1):
                sim = r.get('similarity', 0)
                preview = r['content'][:150].replace('\n', ' ')
                print(f"    {i}. [{sim:.4f}] {preview}...")
        else:
            print(f"  No results found")

    # Test with multi-document retrieval + reranking
    print("\n\n[2] MULTI-DOCUMENT RETRIEVAL WITH RERANKING")
    print("-" * 80)

    retrieval_service = RetrievalService(
        supabase_client=supabase_client,
        embedding_service=embedding_service,
        top_k=10,
        use_reranking=True
    )

    final_results = retrieval_service.retrieve(query, document_name=None)

    print(f"\nTop 10 results after reranking:")
    for i, result in enumerate(final_results, 1):
        doc_name = result.get('document_name', 'unknown')
        rerank_score = result.get('rerank_score', None)
        similarity = result.get('similarity', 0)
        content_preview = result['content'][:120].replace('\n', ' ')

        score_display = f"Rerank: {rerank_score:.4f}" if rerank_score else f"Sim: {similarity:.4f}"
        print(f"  {i:2d}. [{doc_name:30s}] {score_display} | {content_preview}...")

    # Count by document
    print("\n" + "-" * 80)
    print("DISTRIBUTION IN TOP 10:")
    pdp8_count = sum(1 for r in final_results if r.get('document_name') == 'pdp8')
    annexes_count = sum(1 for r in final_results if r.get('document_name') == 'PDP8_full-with-annexes_EN')
    print(f"  pdp8: {pdp8_count} results")
    print(f"  PDP8_full-with-annexes_EN: {annexes_count} results")

    # Show if the correct document is ranked #1
    if final_results:
        top_doc = final_results[0].get('document_name')
        print(f"\n✓ Top result is from: {top_doc}")


async def find_unique_content():
    """Sample content from each document to help identify unique queries."""
    supabase_client = get_supabase_client()

    print("\n" + "=" * 80)
    print("SAMPLING CONTENT FROM EACH DOCUMENT")
    print("=" * 80)

    for doc_name in ["pdp8", "PDP8_full-with-annexes_EN"]:
        print(f"\n{doc_name}:")
        print("-" * 80)

        # Get random chunks
        result = supabase_client.table("documents")\
            .select("content, chunk_id")\
            .eq("document_name", doc_name)\
            .order("chunk_id")\
            .range(10, 15)\
            .execute()

        if result.data:
            for chunk in result.data:
                print(f"\nChunk {chunk['chunk_id']}:")
                print(chunk['content'][:300])
                print("...")


async def main():
    """Main test function."""
    import sys

    if len(sys.argv) > 1:
        # Use provided query
        query = " ".join(sys.argv[1:])
        await test_unique_content_query(query)
    else:
        # Show sample content to help user pick a query
        print("No query provided. Showing sample content from each document...")
        print("Usage: python test_unique_content.py 'your query here'")
        await find_unique_content()


if __name__ == "__main__":
    asyncio.run(main())
