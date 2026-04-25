#!/usr/bin/env python3
"""Cache all documents in the database for fast queries."""

import sys
sys.path.insert(0, '/Users/truongtang/Projects/pdp8-rag')

from app.db.dependencies import get_supabase_client
from app.services.rag.gemini_cache import GeminiCacheService
from app.core.config import get_settings
import time
from collections import defaultdict


def get_all_document_chunks():
    """Get all chunks grouped by document name."""
    client = get_supabase_client()

    # Fetch ALL documents with pagination
    all_data = []
    offset = 0
    page_size = 1000

    print("Fetching documents from database...")
    while True:
        result = client.table("documents")\
            .select("document_name, content, page_range, pages")\
            .range(offset, offset + page_size - 1)\
            .execute()

        if not result.data:
            break

        all_data.extend(result.data)
        print(f"  Loaded {len(all_data)} chunks so far...")

        if len(result.data) < page_size:
            break

        offset += page_size

    print(f"Total chunks loaded: {len(all_data)}\n")

    # Group by document name
    docs = defaultdict(list)
    for row in all_data:
        docs[row['document_name']].append({
            'content': row['content'],
            'page_range': row.get('page_range', 'unknown'),
            'pages': row.get('pages', [])
        })

    return docs


def main():
    print("=" * 80)
    print("CACHING ALL DOCUMENTS")
    print("=" * 80)
    print()

    settings = get_settings()
    cache_service = GeminiCacheService(
        api_key=settings.google_api_key,
        model="gemini-2.5-flash"
    )

    all_docs = get_all_document_chunks()
    total_chunks = sum(len(chunks) for chunks in all_docs.values())
    print(f"Found {len(all_docs)} unique documents with {total_chunks} total chunks\n")

    total_start = time.time()
    success_count = 0
    skip_count = 0
    error_count = 0

    for i, (doc_name, chunks) in enumerate(all_docs.items(), 1):
        print(f"[{i}/{len(all_docs)}] {doc_name}")
        print(f"  Chunks: {len(chunks)}")

        start = time.time()
        try:
            cache_name = cache_service.create_document_cache(
                doc_name=doc_name,
                chunks=chunks,
                ttl_hours=24
            )

            elapsed = time.time() - start

            if cache_name:
                print(f"  ✓ Cached in {elapsed:.1f}s")
                print(f"    {cache_name}")
                success_count += 1
            else:
                print(f"  ⊘ Skipped (too small)")
                skip_count += 1

        except Exception as e:
            elapsed = time.time() - start
            print(f"  ✗ Error in {elapsed:.1f}s: {str(e)[:100]}")
            error_count += 1

        print()

    total_time = time.time() - total_start

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total documents: {len(all_docs)}")
    print(f"  ✓ Successfully cached: {success_count}")
    print(f"  ⊘ Skipped: {skip_count}")
    print(f"  ✗ Errors: {error_count}")
    print(f"\nTotal time: {total_time:.1f}s ({total_time/60:.1f} minutes)")

    if len(all_docs) > 0:
        print(f"Average time per document: {total_time/len(all_docs):.1f}s")


if __name__ == "__main__":
    main()
