"""Test retrieval from vector database."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from app.services.embedding import EmbeddingService
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.core.config import get_settings


async def main():
    """Test retrieval pipeline."""
    # Get configuration
    settings = get_settings()

    # Initialize services
    embedding_service = EmbeddingService(settings)

    # Get database components
    supabase_client = get_supabase_client()
    doc_repo = get_document_repository(supabase_client)

    # Test retrieval
    print("Testing retrieval...")
    test_query = "What is this document about?"

    print(f"\nQuery: {test_query}")
    print("Generating query embedding...")
    query_embedding = embedding_service.embed_query(test_query)

    print(f"Searching for similar documents (embedding dimension: {len(query_embedding)})...")
    results = doc_repo.search_similar(query_embedding, limit=3)

    print(f"\nFound {len(results)} similar chunks:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. Similarity: {result.get('similarity', 0):.4f}")
        print(f"   Document: {result.get('document_name', 'N/A')}")
        print(f"   Chunk ID: {result.get('chunk_id', 'N/A')}")
        print(f"   Content preview: {result['content'][:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
