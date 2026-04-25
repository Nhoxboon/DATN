"""Document management service package."""

from app.services.documents.service import DocumentService
from app.services.documents.dependencies import get_document_service

__all__ = ["DocumentService", "get_document_service"]
