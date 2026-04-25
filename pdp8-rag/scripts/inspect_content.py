"""Inspect and compare content quality between documents in the database."""

import asyncio
from app.core.config import get_settings
from app.db.dependencies import get_supabase_client
from app.services.embedding import EmbeddingService
from app.db.repository import get_document_repository


async def inspect_document_content():
    """Inspect content quality from both documents."""
    # Initialize services
    settings = get_settings()
    supabase_client = get_supabase_client()
    embedding_service = EmbeddingService(settings)

    # Get document repository
    doc_repo = get_document_repository(supabase_client)

    # Documents to compare
    doc1 = "pdp8"
    doc2 = "PDP8_full-with-annexes_EN"

    # Query for testing
    query = "What are the renewable energy targets?"
    print(f"Query: '{query}'\n")
    print("=" * 80)

    # Get query embedding
    query_embedding = embedding_service.embed_text(query)

    # Retrieve from both documents
    for doc_name in [doc1, doc2]:
        print(f"\n{'='*80}")
        print(f"DOCUMENT: {doc_name}")
        print('='*80)

        # Get top results
        results = doc_repo.search_similar(
            query_embedding=query_embedding,
            limit=5,
            document_name=doc_name
        )

        print(f"\nFound {len(results)} chunks")

        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', 0)
            content = result.get('content', '')
            chunk_id = result.get('chunk_id', 'N/A')
            pages = result.get('pages', [])
            page_range = result.get('page_range', 'N/A')

            print(f"\n{'-'*80}")
            print(f"Chunk #{i} (ID: {chunk_id})")
            print(f"Similarity: {similarity:.4f}")
            print(f"Pages: {page_range} (Array: {pages})")
            print(f"Content Length: {len(content)} characters")
            print(f"{'-'*80}")

            # Show full content
            print("CONTENT:")
            print(content)
            print()

            # Analyze content quality
            print("QUALITY METRICS:")
            print(f"  - Characters: {len(content)}")
            print(f"  - Words: {len(content.split())}")
            print(f"  - Lines: {content.count(chr(10)) + 1}")
            print(f"  - Has newlines: {chr(10) in content}")
            print(f"  - Has tabs: {chr(9) in content}")
            print(f"  - Alphanumeric ratio: {sum(c.isalnum() for c in content) / len(content):.2%}")
            print(f"  - Whitespace ratio: {sum(c.isspace() for c in content) / len(content):.2%}")

            # Check for common issues
            issues = []
            if content.count('\n\n') > len(content) / 100:
                issues.append("Excessive blank lines")
            if len(content.split()) < 50:
                issues.append("Very short chunk")
            if sum(c.isalnum() for c in content) / len(content) < 0.6:
                issues.append("Low alphanumeric ratio (formatting issues?)")
            if any(ord(c) > 127 for c in content):
                issues.append("Contains non-ASCII characters")

            if issues:
                print(f"  - ISSUES: {', '.join(issues)}")
            else:
                print(f"  - No obvious issues detected")

            print()

    print("\n" + "="*80)
    print("COMPARISON SUMMARY")
    print("="*80)

    # Get all chunks from each document (first 10)
    print(f"\nRetrieving first 10 chunks from each document for statistical comparison...")

    for doc_name in [doc1, doc2]:
        # Query directly from supabase to get raw chunks
        result = supabase_client.table("documents")\
            .select("content, chunk_id")\
            .eq("document_name", doc_name)\
            .order("chunk_id")\
            .limit(10)\
            .execute()

        if result.data:
            chunks = result.data
            print(f"\n{doc_name}:")
            print(f"  Chunks analyzed: {len(chunks)}")

            avg_length = sum(len(c['content']) for c in chunks) / len(chunks)
            avg_words = sum(len(c['content'].split()) for c in chunks) / len(chunks)

            print(f"  Average chunk length: {avg_length:.1f} characters")
            print(f"  Average words per chunk: {avg_words:.1f}")

            # Check first chunk in detail
            first_chunk = chunks[0]['content']
            print(f"\n  First chunk preview (ID: {chunks[0]['chunk_id']}):")
            print(f"  {first_chunk[:200]}...")


if __name__ == "__main__":
    asyncio.run(inspect_document_content())
