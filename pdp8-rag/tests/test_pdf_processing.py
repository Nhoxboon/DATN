"""Test PDF processing with marker and semantic chunking."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from app.services.pdf_processor import PDFProcessor
from app.services.embedding import EmbeddingService
from app.services.storage import StorageService
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository


async def main():
    """Test PDF processing pipeline."""
    from app.core.config import get_settings, get_app_config

    # Get configuration
    settings = get_settings()
    app_config = get_app_config()

    # Initialize services with DI
    embedding_service = EmbeddingService(settings)
    pdf_processor = PDFProcessor(app_config, settings, embedding_service)

    # Get database components
    supabase_client = get_supabase_client()
    doc_repo = get_document_repository(supabase_client)
    storage_service = StorageService(supabase_client)

    # Process PDF
    pdf_path = "uploads/sample-local-pdf.pdf"

    if not Path(pdf_path).exists():
        print(f"Error: PDF file not found at {pdf_path}")
        return

    print(f"Processing PDF: {pdf_path}")

    # Step 0: Upload PDF to Supabase Storage
    print("\nStep 0: Uploading PDF to Supabase Storage...")
    upload_result = storage_service.upload_pdf(pdf_path)
    print(f"Uploaded to: {upload_result['path']}")
    print(f"Public URL: {upload_result['public_url']}")

    # Step 1: Extract markdown from PDF
    print("Step 1: Extracting markdown from PDF...")
    markdown_content = pdf_processor.process_pdf(pdf_path)
    print(f"Extracted {len(markdown_content)} characters")

    # Step 2: Chunk the content
    print("\nStep 2: Chunking content...")
    chunks = pdf_processor.chunk_text(markdown_content)
    print(f"Created {len(chunks)} chunks")

    # Step 3: Generate embeddings and store
    print("\nStep 3: Generating embeddings and storing in database...")
    document_name = Path(pdf_path).stem

    for chunk in chunks:
        # Generate embedding
        embedding = embedding_service.embed_text(chunk["text"])

        # Store in database
        doc_repo.insert_chunk(
            document_name=document_name,
            chunk_id=chunk["chunk_id"],
            content=chunk["text"],
            embedding=embedding,
            metadata={
                "start_index": chunk["start_index"],
                "end_index": chunk["end_index"],
                "token_count": chunk["token_count"]
            }
        )
        print(f"  Stored chunk {chunk['chunk_id']} ({chunk['token_count']} tokens)")

    print("\nProcessing complete!")

    # Test retrieval
    print("\nStep 4: Testing retrieval...")
    test_query = "What is this document about?"
    query_embedding = embedding_service.embed_query(test_query)
    results = doc_repo.search_similar(query_embedding, limit=3)

    print(f"\nQuery: {test_query}")
    print(f"Found {len(results)} similar chunks:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. Similarity: {result.get('similarity', 0):.4f}")
        print(f"   Content preview: {result['content'][:200]}...")


if __name__ == "__main__":
    asyncio.run(main())
