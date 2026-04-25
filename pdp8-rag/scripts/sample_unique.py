"""Quick script to find unique content in pdp8."""

import asyncio
from app.db.dependencies import get_supabase_client


async def sample_documents():
    """Sample chunks from both documents to identify unique content."""
    supabase_client = get_supabase_client()

    print("=" * 80)
    print("SAMPLING CONTENT TO IDENTIFY UNIQUE INFORMATION")
    print("=" * 80)

    # Get total chunks from each
    for doc_name in ["pdp8", "PDP8_full-with-annexes_EN"]:
        result = supabase_client.table("documents")\
            .select("chunk_id", count="exact")\
            .eq("document_name", doc_name)\
            .execute()

        count = result.count if hasattr(result, 'count') else 0
        print(f"\n{doc_name}: {count} total chunks")

    # Sample from middle of pdp8 (where unique content might be)
    print("\n" + "=" * 80)
    print("SAMPLE FROM pdp8 (chunks 15-25):")
    print("=" * 80)

    result = supabase_client.table("documents")\
        .select("content, chunk_id, pages")\
        .eq("document_name", "pdp8")\
        .order("chunk_id")\
        .range(15, 25)\
        .execute()

    if result.data:
        for chunk in result.data:
            print(f"\n--- Chunk {chunk['chunk_id']} (Pages: {chunk.get('pages', 'N/A')}) ---")
            # Show first 400 chars
            content = chunk['content'][:400]
            print(content)
            if len(chunk['content']) > 400:
                print("...")

    print("\n" + "=" * 80)
    print("SAMPLE FROM PDP8_full-with-annexes_EN (chunks 15-25):")
    print("=" * 80)

    result = supabase_client.table("documents")\
        .select("content, chunk_id, pages")\
        .eq("document_name", "PDP8_full-with-annexes_EN")\
        .order("chunk_id")\
        .range(15, 25)\
        .execute()

    if result.data:
        for chunk in result.data:
            print(f"\n--- Chunk {chunk['chunk_id']} (Pages: {chunk.get('pages', 'N/A')}) ---")
            content = chunk['content'][:400]
            print(content)
            if len(chunk['content']) > 400:
                print("...")


if __name__ == "__main__":
    asyncio.run(sample_documents())
