"""Document service dependencies."""

from functools import lru_cache
from app.services.documents.service import DocumentService
from app.services.pdf_processor.processor import PDFProcessor
from app.services.embedding import EmbeddingService
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.core.config import get_settings, get_app_config


@lru_cache()
def get_document_service() -> DocumentService:
    """
    Get document service instance (singleton).

    Returns:
        DocumentService instance
    """
    settings = get_settings()
    app_config = get_app_config()
    supabase_client = get_supabase_client()

    # Initialize dependencies
    embedding_service = EmbeddingService(settings)
    doc_repository = get_document_repository(supabase_client)
    pdf_processor = PDFProcessor(app_config, settings, embedding_service)

    return DocumentService(
        supabase_client=supabase_client,
        embedding_service=embedding_service,
        doc_repository=doc_repository,
        pdf_processor=pdf_processor
    )
