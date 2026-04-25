"""Compare the document structure and markdown extraction quality."""

import asyncio
from app.db.dependencies import get_supabase_client


async def compare_document_structure():
    """Compare structure of first 20 chunks from each document."""
    supabase_client = get_supabase_client()

    doc1 = "pdp8"
    doc2 = "PDP8_full-with-annexes_EN"

    for doc_name in [doc1, doc2]:
        print(f"\n{'='*80}")
        print(f"DOCUMENT: {doc_name}")
        print('='*80)

        # Get first 20 chunks
        result = supabase_client.table("documents")\
            .select("content, chunk_id, pages")\
            .eq("document_name", doc_name)\
            .order("chunk_id")\
            .limit(20)\
            .execute()

        if result.data:
            chunks = result.data
            lengths = [len(c['content']) for c in chunks]

            print(f"\nTotal chunks analyzed: {len(chunks)}")
            print(f"Average length: {sum(lengths) / len(lengths):.1f} chars")
            print(f"Min: {min(lengths)}, Max: {max(lengths)}")
            print(f"Std dev: {(sum((x - sum(lengths)/len(lengths))**2 for x in lengths) / len(lengths))**0.5:.1f}")

            # Show distribution
            print("\nChunk length distribution:")
            bins = [0, 200, 400, 600, 800, 1000, 1500, 2000, 10000]
            bin_labels = ["0-200", "200-400", "400-600", "600-800", "800-1000", "1000-1500", "1500-2000", "2000+"]

            for i in range(len(bins) - 1):
                count = sum(1 for l in lengths if bins[i] <= l < bins[i+1])
                if count > 0:
                    bar = "█" * count
                    print(f"  {bin_labels[i]:>12}: {bar} ({count})")

            # Show structure patterns
            print("\nFirst 5 chunks (showing first 200 chars):")
            for i, chunk in enumerate(chunks[:5]):
                content_preview = chunk['content'][:200].replace('\n', ' ')
                print(f"\n  Chunk {i} ({len(chunk['content'])} chars):")
                print(f"    {content_preview}...")

                # Count structural elements
                content = chunk['content']
                print(f"    Lines: {content.count(chr(10)) + 1}")
                print(f"    Bullets (-/+): {content.count('- ') + content.count('+ ')}")
                print(f"    Headers (#): {content.count('##')}")


if __name__ == "__main__":
    asyncio.run(compare_document_structure())
