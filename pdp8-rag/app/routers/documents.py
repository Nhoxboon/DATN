"""Document management API endpoints."""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.services.documents import DocumentService, get_document_service
from app.db.dependencies import get_supabase_client
from app.db.repository import get_document_repository
from app.schemas.documents import (
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentUploadRequest,
    DocumentDeleteResponse
)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    """
    List all available documents in the database.

    Returns:
        List of document names with count
    """
    try:
        # Don't use DocumentService here to avoid initializing PDFProcessor
        supabase_client = get_supabase_client()
        doc_repo = get_document_repository(supabase_client)
        documents = doc_repo.list_documents()
        return DocumentListResponse(documents=documents, count=len(documents))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {str(e)}")


@router.post("/upload/file", response_model=DocumentUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service)
) -> DocumentUploadResponse:
    """
    Upload a PDF document via file upload.

    Args:
        file: PDF file to upload

    Returns:
        Upload status with document info
    """
    try:
        # Validate file type
        if not file.filename or not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Read file content
        content = await file.read()

        # Upload and process
        result = service.upload_from_bytes(
            file_content=content,
            filename=file.filename
        )

        return DocumentUploadResponse(
            status="success",
            document_name=result["document_name"],
            chunks_processed=result["chunks_processed"],
            storage_path=result["storage_path"],
            public_url=result.get("public_url")
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.post("/upload/path", response_model=DocumentUploadResponse)
async def upload_from_path(
    request: DocumentUploadRequest,
    service: DocumentService = Depends(get_document_service)
) -> DocumentUploadResponse:
    """
    Upload a PDF document from a file path (for server-side uploads).

    Args:
        request: Upload request with file path

    Returns:
        Upload status with document info
    """
    try:
        result = service.upload_document(
            file_path=request.file_path,
            document_name=request.document_name
        )

        return DocumentUploadResponse(
            status="success",
            document_name=result["document_name"],
            chunks_processed=result["chunks_processed"],
            storage_path=result["storage_path"],
            public_url=result.get("public_url")
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


@router.delete("/{document_name}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_name: str,
    service: DocumentService = Depends(get_document_service)
) -> DocumentDeleteResponse:
    """
    Delete a document and all its chunks from the database and storage.

    Args:
        document_name: Name of the document to delete

    Returns:
        Deletion status
    """
    try:
        success = service.delete_document(document_name)

        if success:
            return DocumentDeleteResponse(
                status="success",
                document_name=document_name,
                message=f"Document '{document_name}' deleted successfully"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {str(e)}")
